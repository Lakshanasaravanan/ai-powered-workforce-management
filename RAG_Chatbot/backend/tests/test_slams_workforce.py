from __future__ import annotations

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.schemas.workforce import AttendancePeriod
from app.services.slams import DelegationTokenSigner, SLAMSClient, SLAMSWorkforceProvider
from app.services.workforce import (
    WorkforceBusinessError,
    WorkforceContractError,
    WorkforceForbidden,
    WorkforceNotFound,
    WorkforceUnauthorized,
    WorkforceUnavailable,
)


@pytest.fixture
def private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def signer(private_key: str) -> DelegationTokenSigner:
    return DelegationTokenSigner("agentic-rag-service", "slams-internal-api", private_key, 300)


def make_provider(handler, signer: DelegationTokenSigner) -> SLAMSWorkforceProvider:
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://slams.test")
    return SLAMSWorkforceProvider(SLAMSClient("https://slams.test", signer, 0.1, 0.1, client))


def test_delegation_signer_has_required_rs256_claims_and_unique_jti(signer: DelegationTokenSigner):
    first, second = signer.sign("EMP001"), signer.sign("EMP001")
    assert jwt.get_unverified_header(first)["alg"] == "RS256"
    claims = jwt.decode(first, options={"verify_signature": False})
    assert claims["iss"] == "agentic-rag-service"
    assert claims["aud"] == "slams-internal-api"
    assert claims["sub"] == claims["employee_id"] == "EMP001"
    assert claims["token_type"] == "delegation"
    assert "roles" not in claims
    assert 0 < claims["exp"] - claims["iat"] <= 300
    assert claims["jti"] != jwt.decode(second, options={"verify_signature": False})["jti"]


def test_profile_mapping_sends_delegation_and_request_id(signer: DelegationTokenSigner):
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["path"] = request.url.path
        observed["authorization"] = request.headers.get("Authorization")
        observed["request_id"] = request.headers.get("X-Request-ID")
        return httpx.Response(200, json={"employeeId": "EMP001", "fullName": "Avery", "department": "People", "designation": "Engineer"})

    profile = make_provider(handler, signer).get_profile("EMP001", "2f6cae4f-09ea-4511-a49d-cb3988930ef2")
    assert profile.employee_id == "EMP001"
    assert profile.display_name == "Avery"
    assert profile.synthetic_data is False
    assert observed["path"] == "/api/employees/me"
    assert observed["authorization"].startswith("Bearer ")
    assert observed["request_id"] == "2f6cae4f-09ea-4511-a49d-cb3988930ef2"


def test_leave_and_attendance_mapping(signer: DelegationTokenSigner):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/leaves/balance":
            return httpx.Response(200, json={"casualLeave": 2, "sickLeave": 3, "earnedLeave": 4})
        return httpx.Response(200, json={"attendancePercentage": 90.0, "presentCount": 18, "lateCount": 1, "halfDayCount": 1, "absentCount": 2, "totalDays": 22})

    provider = make_provider(handler, signer)
    leave = provider.get_leave_balance("EMP001")
    attendance = provider.get_attendance_summary("EMP001", AttendancePeriod.SLAMS_AGGREGATE)
    assert (leave.annual_days_remaining, leave.casual_days_remaining, leave.earned_days_remaining, leave.sick_days_remaining) == (6, 2, 4, 3)
    assert (attendance.scheduled_days, attendance.present_days, attendance.late_days, attendance.half_days, attendance.absent_days) == (22, 18, 1, 1, 2)
    assert attendance.leave_days == 0 and attendance.synthetic_data is False


@pytest.mark.parametrize(("status_code", "exception"), [
    (400, WorkforceBusinessError), (401, WorkforceUnauthorized), (403, WorkforceForbidden),
    (404, WorkforceNotFound), (409, WorkforceBusinessError), (500, WorkforceUnavailable),
])
def test_safe_status_mapping(status_code, exception, signer: DelegationTokenSigner):
    provider = make_provider(lambda request: httpx.Response(status_code, json={"message": "do not expose"}), signer)
    with pytest.raises(exception):
        provider.get_profile("EMP001")


def test_malformed_json_schema_and_employee_spoofing_are_contract_errors(signer: DelegationTokenSigner):
    malformed = make_provider(lambda request: httpx.Response(200, content=b"not-json"), signer)
    missing_field = make_provider(lambda request: httpx.Response(200, json={"employeeId": "EMP001"}), signer)
    spoofed = make_provider(lambda request: httpx.Response(200, json={"employeeId": "EMP002", "fullName": "Other"}), signer)
    for provider in (malformed, missing_field, spoofed):
        with pytest.raises(WorkforceContractError):
            provider.get_profile("EMP001")


def test_timeout_and_transient_reads_retry_once(signer: DelegationTokenSigner):
    attempts = 0

    def transient(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503 if attempts == 1 else 200, json={"employeeId": "EMP001", "fullName": "Avery"})

    assert make_provider(transient, signer).get_profile("EMP001").employee_id == "EMP001"
    assert attempts == 2
    timeout = make_provider(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout", request=request)), signer)
    with pytest.raises(WorkforceUnavailable):
        timeout.get_profile("EMP001")


def test_auth_errors_do_not_retry(signer: DelegationTokenSigner):
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401)

    with pytest.raises(WorkforceUnauthorized):
        make_provider(handler, signer).get_profile("EMP001")
    assert attempts == 1


@pytest.mark.parametrize("period", [AttendancePeriod.CURRENT_MONTH, AttendancePeriod.LAST_30_DAYS])
def test_date_filtered_periods_are_rejected_without_making_a_fabricated_request(period, signer: DelegationTokenSigner):
    provider = make_provider(lambda request: pytest.fail("HTTP request should not occur"), signer)
    with pytest.raises(WorkforceBusinessError):
        provider.get_attendance_summary("EMP001", period)
