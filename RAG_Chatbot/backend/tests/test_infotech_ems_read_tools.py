"""Phase 5 Step 1 tests for the isolated, read-only InfoTech EMS boundary."""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.agents.models import InfoTechAgentExecutionContext, infotech_agent_context
from app.core.ems_auth import EMSIdentity
from app.core.config import Settings
from app.services.infotech_ems import (
    EMSConflict,
    EMSContractError,
    EMSForbidden,
    EMSNotFound,
    EMSRateLimited,
    EMSUnavailable,
    EMSUnauthorized,
    EMSValidationFailure,
    InfoTechEMSReadClient,
)
from app.tools.infotech_ems import (
    InfoTechInvalidToolInput,
    InfoTechReadToolRegistry,
    InfoTechUnauthorizedTool,
    InfoTechUnknownTool,
    build_infotech_read_registry,
)


ACTOR_ID = uuid4()
MANAGER_ID = uuid4()
LEAVE_ID = uuid4()
NOTIFICATION_ID = uuid4()
BEARER = "request-lifetime-test-bearer"


def profile(*, role: str = "EMPLOYEE") -> dict[str, object]:
    return {
        "id": str(ACTOR_ID), "employee_code": "INF1001", "full_name": "Test Employee",
        "company_email": "INF1001@infotech.local", "role": role, "designation": "Engineer",
        "department": "Engineering", "manager_id": str(MANAGER_ID), "is_active": True,
    }


def leave() -> dict[str, object]:
    return {
        "id": str(LEAVE_ID), "employee": {"id": str(ACTOR_ID), "employee_code": "INF1001", "full_name": "Test Employee"},
        "leave_type": "CASUAL", "status": "PENDING", "start_date": "2026-10-01", "end_date": "2026-10-01",
        "duration": "FULL_DAY", "half_day_period": None, "reason": "Personal", "approval_required": True,
        "decided_by_id": None, "decided_at": None, "decision_note": None, "decision_source": None,
        "manager_notification_delivered": True, "created_at": "2026-09-15T10:00:00", "updated_at": "2026-09-15T10:00:00",
    }


def notification() -> dict[str, object]:
    return {
        "id": str(NOTIFICATION_ID), "category": "LEAVE", "title": "Leave approval required", "message": "A leave request needs review.",
        "is_read": False, "read_at": None, "related_entity_type": "LEAVE_REQUEST", "related_entity_id": str(LEAVE_ID),
        "created_at": "2026-09-15T10:00:00",
    }


def context(role: str = "EMPLOYEE") -> InfoTechAgentExecutionContext:
    return InfoTechAgentExecutionContext(ACTOR_ID, "INF1001", "Test Employee", role, "request-id", uuid4())


def settings() -> Settings:
    return Settings(_env_file=None, environment="test", ems_api_base_url="http://ems.test")


def make_client(handler) -> InfoTechEMSReadClient:
    return InfoTechEMSReadClient(settings(), httpx.Client(transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize(
    ("method", "path", "payload", "expected_type"),
    [
        ("get_my_profile", "/api/v1/auth/me", profile(), "EMSProfile"),
        ("get_my_manager", "/api/v1/employees/me/manager", {"manager": profile(role="MANAGER")}, "EMSManagerResult"),
        ("get_my_leaves", "/api/v1/leaves/me", [leave()], "list"),
        ("get_my_notifications", "/api/v1/notifications", [notification()], "list"),
        ("get_unread_notification_count", "/api/v1/notifications/unread-count", {"unread_count": 3}, "EMSUnreadCount"),
        ("get_direct_reports", "/api/v1/employees/me/direct-reports", [profile(role="EMPLOYEE")], "list"),
        ("get_team_leaves", "/api/v1/leaves/team", [leave()], "list"),
    ],
)
def test_each_explicit_read_operation_uses_fixed_get_path_and_current_bearer(method, path, payload, expected_type):
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update({"method": request.method, "path": request.url.path, "authorization": request.headers.get("Authorization")})
        return httpx.Response(200, json=payload)

    result = getattr(make_client(handler), method)(BEARER)
    assert captured == {"method": "GET", "path": path, "authorization": f"Bearer {BEARER}"}
    assert type(result).__name__ == expected_type


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, EMSUnauthorized), (403, EMSForbidden), (404, EMSNotFound),
        (409, EMSConflict), (422, EMSValidationFailure), (429, EMSRateLimited),
        (500, EMSUnavailable),
    ],
)
def test_ems_status_errors_fail_closed(status, error):
    client = make_client(lambda _: httpx.Response(status, json={"detail": "not exposed"}))
    with pytest.raises(error):
        client.get_my_profile(BEARER)


def test_timeout_and_malformed_ems_response_fail_closed():
    timeout_client = make_client(lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("timeout")))
    with pytest.raises(EMSUnavailable):
        timeout_client.get_my_profile(BEARER)
    malformed_client = make_client(lambda _: httpx.Response(200, json={"id": str(ACTOR_ID)}))
    with pytest.raises(EMSContractError):
        malformed_client.get_my_profile(BEARER)


def test_registry_has_exact_seven_read_tools_and_no_generic_transport_surface():
    registry = build_infotech_read_registry(make_client(lambda _: httpx.Response(200, json=profile())))
    assert registry.names() == frozenset({
        "get_my_profile", "get_my_manager", "get_my_leaves", "get_my_notifications", "get_unread_notification_count", "get_direct_reports", "get_team_leaves",
    })
    assert not hasattr(registry, "register")
    assert not hasattr(registry, "request")


@pytest.mark.parametrize("arguments", [
    {"employee_id": str(uuid4())}, {"manager_id": str(uuid4())}, {"role": "MANAGER"},
    {"url": "https://untrusted.test"}, {"bearer_token": "forged"}, {"path": "/api/v1/employees"},
])
def test_empty_tool_inputs_reject_identity_transport_and_url_injection(arguments):
    registry = build_infotech_read_registry(make_client(lambda _: httpx.Response(200, json=profile())))
    with pytest.raises(InfoTechInvalidToolInput):
        registry.execute("get_my_profile", context(), BEARER, arguments)


def test_unknown_tool_fails_closed_without_any_http_call():
    called = False

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=profile())

    registry = build_infotech_read_registry(make_client(handler))
    with pytest.raises(InfoTechUnknownTool):
        registry.execute("arbitrary_http", context(), BEARER, {})
    assert called is False


def test_agent_role_policy_allows_personal_reads_and_manager_only_tools():
    registry = build_infotech_read_registry(make_client(lambda _: httpx.Response(200, json=[])))
    personal = frozenset({"get_my_profile", "get_my_manager", "get_my_leaves", "get_my_notifications", "get_unread_notification_count"})
    assert registry.names_for(context("EMPLOYEE")) == personal
    assert registry.names_for(context("ADMIN")) == personal
    assert registry.names_for(context("MANAGER")) == personal | {"get_direct_reports", "get_team_leaves"}
    with pytest.raises(InfoTechUnauthorizedTool):
        registry.execute("get_direct_reports", context("ADMIN"), BEARER, {})
    with pytest.raises(InfoTechUnauthorizedTool):
        registry.execute("get_team_leaves", context("EMPLOYEE"), BEARER, {})


def test_context_is_identity_only_and_bearer_never_appears_in_tool_result_or_context_repr():
    server_context = context("MANAGER")
    assert "bearer" not in repr(server_context).lower()
    assert BEARER not in repr(server_context)
    client = make_client(lambda _: httpx.Response(200, json={"unread_count": 1}))
    result = build_infotech_read_registry(client).execute("get_unread_notification_count", server_context, BEARER, {})
    assert BEARER not in result.model_dump_json()


def test_context_is_derived_from_verified_ems_identity_not_tool_arguments():
    identity = EMSIdentity(ACTOR_ID, "INF1001", "Test Employee", "MANAGER")
    derived = infotech_agent_context(identity, "request-id", uuid4())
    assert derived.employee_id == ACTOR_ID and derived.employee_code == "INF1001" and derived.role == "MANAGER"
