from __future__ import annotations

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.audit import AuditEvent, AuditSource
from app.models.employee import Employee, Role
from app.models.idempotency import MutationIdempotency
from app.models.leave import LeaveRequest, LeaveStatus
from app.models.notification import Notification


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine)
client = TestClient(app)


def override_db():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolated_database():
    app.dependency_overrides[get_db] = override_db
    yield
    app.dependency_overrides.pop(get_db, None)


def employee(code: str, manager_id=None) -> Employee:
    db = Session()
    value = Employee(employee_code=code, full_name=code, company_email=f"{code}@infotech.local", role=Role.EMPLOYEE, designation="Engineer", department="Engineering", password_hash=hash_password("test-password"), onboarding_completed=True, is_active=True, manager_id=manager_id)
    db.add(value); db.commit(); db.refresh(value); db.close()
    return value


def headers(user: Employee, key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(str(user.id))}", "X-InfoTech-Agent": "1", "Idempotency-Key": key, "X-Request-ID": "phase5-test"}


def body(reason="private"):
    return {"leave_type": "CASUAL", "start_date": "2027-10-01", "end_date": "2027-10-01", "duration": "FULL_DAY", "reason": reason}


def test_agent_leave_idempotency_audit_and_actor_isolation():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    manager = employee("MANAGER")
    first = employee("FIRST", manager.id)
    second = employee("SECOND", manager.id)
    key = "server-generated-idempotency-key-for-test-0001"
    one = client.post("/api/v1/leaves", json=body(), headers=headers(first, key))
    replay = client.post("/api/v1/leaves", json=body(), headers=headers(first, key))
    conflict = client.post("/api/v1/leaves", json=body("different"), headers=headers(first, key))
    isolated = client.post("/api/v1/leaves", json=body(), headers=headers(second, key))
    assert one.status_code == 201 and replay.status_code == 201 and replay.json()["id"] == one.json()["id"]
    assert conflict.status_code == 409 and isolated.status_code == 201
    db = Session()
    assert db.query(LeaveRequest).count() == 2
    assert db.query(Notification).count() == 2
    assert db.query(MutationIdempotency).count() == 2
    audits = db.query(AuditEvent).all()
    assert len(audits) == 2 and all(a.source is AuditSource.AI_AGENT for a in audits)
    assert all("reason" not in (a.after_state or {}) for a in audits)
    db.close()


def test_normal_leave_remains_compatible_without_agent_headers():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    user = employee("NORMAL")
    response = client.post("/api/v1/leaves", json=body(), headers={"Authorization": f"Bearer {token(str(user.id))}"})
    assert response.status_code == 201
    db = Session(); assert db.query(MutationIdempotency).count() == db.query(AuditEvent).count() == 0; db.close()


@pytest.mark.parametrize(("endpoint", "expected", "note"), [
    ("approve", "APPROVED", None), ("reject", "REJECTED", "coverage unavailable"),
])
def test_agent_manager_decision_idempotency_audit_and_ui_compatibility(endpoint, expected, note):
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    manager = Employee(employee_code="MANAGER", full_name="Manager", company_email="MANAGER@infotech.local", role=Role.MANAGER, designation="Manager", department="Engineering", password_hash=hash_password("test-password"), onboarding_completed=True, is_active=True)
    db = Session(); db.add(manager); db.commit(); db.refresh(manager); db.close()
    requester = employee("REQUESTER", manager.id)
    created = client.post("/api/v1/leaves", json=body(), headers={"Authorization": f"Bearer {token(str(requester.id))}"})
    assert created.status_code == 201
    key = f"decision-idempotency-key-{endpoint}-0001"
    request_headers = headers(manager, key)
    first = client.post(f"/api/v1/leaves/{created.json()['id']}/{endpoint}", json={"decision_note": note}, headers=request_headers)
    replay = client.post(f"/api/v1/leaves/{created.json()['id']}/{endpoint}", json={"decision_note": note}, headers=request_headers)
    conflict = client.post(f"/api/v1/leaves/{created.json()['id']}/{endpoint}", json={"decision_note": "different"}, headers=request_headers)
    assert first.status_code == replay.status_code == 200
    assert first.json()["status"] == replay.json()["status"] == expected
    assert conflict.status_code == 409
    db = Session()
    assert db.query(LeaveRequest).one().status.value == expected
    assert db.query(Notification).count() == 2  # initial manager request + one requester decision notice
    decisions = db.query(MutationIdempotency).filter_by(operation=f"{endpoint}_leave").all()
    audits = db.query(AuditEvent).filter_by(operation=f"{endpoint}_leave").all()
    assert len(decisions) == len(audits) == 1
    assert audits[0].source is AuditSource.AI_AGENT and "decision_note" not in (audits[0].after_state or {})
    db.close()
