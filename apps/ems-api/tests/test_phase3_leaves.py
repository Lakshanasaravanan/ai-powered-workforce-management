from datetime import date
from uuid import UUID

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.api.routes.leaves import apply_manager_decision
from app.models.employee import Employee, Role
from app.models.leave import DecisionSource, LeaveRequest, LeaveStatus
from app.models.notification import Notification, NotificationCategory


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Session = sessionmaker(engine)
Base.metadata.create_all(engine)


def db_override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_database():
    app.dependency_overrides[get_db] = db_override
    yield
    app.dependency_overrides.pop(get_db, None)


def make_employee(code: str, role: Role = Role.EMPLOYEE, manager_id=None) -> Employee:
    db = Session()
    employee = Employee(
        employee_code=code,
        full_name=code,
        company_email=f"{code}@infotech.local",
        role=role,
        designation="Engineer",
        department="Engineering",
        password_hash=hash_password("test-password"),
        onboarding_completed=True,
        is_active=True,
        manager_id=manager_id,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    db.close()
    return employee


def headers(employee: Employee) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(str(employee.id))}"}


def setup():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    admin = make_employee("ADMIN", Role.ADMIN)
    manager = make_employee("MANAGER", Role.MANAGER)
    employee = make_employee("EMPLOYEE", manager_id=manager.id)
    other = make_employee("OTHER")
    return admin, manager, employee, other


def create(employee: Employee, **overrides):
    body = {
        "leave_type": "CASUAL",
        "start_date": "2026-10-01",
        "end_date": "2026-10-02",
        "duration": "FULL_DAY",
        "reason": "Personal time",
    }
    body.update(overrides)
    return client.post("/api/v1/leaves", json=body, headers=headers(employee))


def notifications_for(employee: Employee) -> list[Notification]:
    db = Session()
    notifications = db.query(Notification).filter_by(recipient_id=employee.id).all()
    db.expunge_all()
    db.close()
    return notifications


def test_leave_creation_policy_and_identity_are_server_derived():
    _, _, employee, other = setup()
    casual = create(employee)
    emergency = create(employee, leave_type="EMERGENCY")
    day_off = create(
        employee,
        leave_type="DAY_OFF",
        start_date="2026-10-03",
        end_date="2026-10-03",
        duration="HALF_DAY",
        half_day_period="MORNING",
    )
    medical = create(employee, leave_type="MEDICAL")
    assert casual.status_code == emergency.status_code == day_off.status_code == medical.status_code == 201
    assert casual.json()["status"] == emergency.json()["status"] == day_off.json()["status"] == "PENDING"
    assert day_off.json()["duration"] == "HALF_DAY"
    assert day_off.json()["half_day_period"] == "MORNING"
    assert medical.json()["status"] == "APPROVED"
    assert medical.json()["approval_required"] is False
    assert medical.json()["decided_by_id"] is None
    assert medical.json()["decision_source"] == "AUTOMATIC_POLICY"
    spoofed = create(employee, employee_id=str(other.id), status="APPROVED", approval_required=False)
    assert spoofed.status_code == 201
    assert spoofed.json()["employee"]["id"] == str(employee.id)
    assert spoofed.json()["status"] == "PENDING"


def test_leave_validation_rejects_invalid_dates_and_day_off_shape():
    _, _, employee, _ = setup()
    assert create(employee, start_date="2026-10-02", end_date="2026-10-01").status_code == 422
    assert create(employee, leave_type="DAY_OFF", duration="FULL_DAY").status_code == 422
    assert create(
        employee,
        leave_type="DAY_OFF",
        start_date="2026-10-03",
        end_date="2026-10-03",
        duration="HALF_DAY",
    ).status_code == 422


def test_leave_visibility_is_scoped_to_self_direct_manager_and_admin():
    admin, manager, employee, other = setup()
    response = create(employee)
    leave_id = response.json()["id"]
    assert client.get("/api/v1/leaves/me", headers=headers(employee)).status_code == 200
    assert client.get(f"/api/v1/leaves/{leave_id}", headers=headers(employee)).status_code == 200
    assert client.get(f"/api/v1/leaves/{leave_id}", headers=headers(manager)).status_code == 200
    assert client.get(f"/api/v1/leaves/{leave_id}", headers=headers(admin)).status_code == 200
    assert client.get(f"/api/v1/leaves/{leave_id}", headers=headers(other)).status_code == 403
    team = client.get("/api/v1/leaves/team", headers=headers(manager))
    assert team.status_code == 200 and [item["id"] for item in team.json()] == [leave_id]
    assert client.get("/api/v1/leaves/team", headers=headers(other)).status_code == 403
    assert client.get("/api/v1/leaves/team", headers=headers(admin)).status_code == 403


def test_medical_decision_metadata_is_automatic_without_approver():
    _, manager, employee, _ = setup()
    response = create(employee, leave_type="MEDICAL")
    assert response.status_code == 201
    payload = response.json()
    assert payload["decided_at"] is not None
    assert payload["decided_by_id"] is None
    db = Session()
    from uuid import UUID

    stored = db.get(LeaveRequest, UUID(payload["id"]))
    assert stored.decided_by_id is None
    assert stored.approval_required is False
    assert stored.decision_source is DecisionSource.AUTOMATIC_POLICY
    db.close()


def test_direct_manager_can_approve_all_approval_required_leave_types():
    _, manager, employee, _ = setup()
    for leave_type, overrides in (
        ("CASUAL", {}),
        ("EMERGENCY", {}),
        (
            "DAY_OFF",
            {
                "start_date": "2026-10-03",
                "end_date": "2026-10-03",
                "duration": "HALF_DAY",
                "half_day_period": "AFTERNOON",
            },
        ),
    ):
        request = create(employee, leave_type=leave_type, **overrides)
        response = client.post(
            f"/api/v1/leaves/{request.json()['id']}/approve",
            json={"decision_note": "Approved"},
            headers=headers(manager),
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "APPROVED"
        assert payload["decided_by_id"] == str(manager.id)
        assert payload["decided_at"] is not None
        assert payload["decision_source"] == "MANAGER"


def test_direct_manager_can_reject_and_note_persists():
    _, manager, employee, _ = setup()
    request = create(employee, leave_type="EMERGENCY")
    response = client.post(
        f"/api/v1/leaves/{request.json()['id']}/reject",
        json={"decision_note": "Operational coverage is required."},
        headers=headers(manager),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
    assert response.json()["decision_note"] == "Operational coverage is required."
    assert response.json()["decided_by_id"] == str(manager.id)
    assert response.json()["decision_source"] == "MANAGER"


def test_decision_authorization_is_direct_manager_only():
    admin, manager, employee, other = setup()
    unrelated_manager = make_employee("OTHER_MANAGER", Role.MANAGER)
    request = create(employee)
    endpoint = f"/api/v1/leaves/{request.json()['id']}/approve"
    for actor in (employee, other, unrelated_manager, admin):
        assert client.post(endpoint, json={}, headers=headers(actor)).status_code == 403
    assert client.post(endpoint, json={}, headers=headers(manager)).status_code == 200


def test_manager_hierarchy_decision_scope_and_medical_protection():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    senior = make_employee("SENIOR", Role.MANAGER)
    manager = make_employee("MANAGER", Role.MANAGER, manager_id=senior.id)
    employee = make_employee("EMPLOYEE", manager_id=manager.id)
    employee_request = create(employee)
    employee_endpoint = f"/api/v1/leaves/{employee_request.json()['id']}/approve"
    assert client.post(employee_endpoint, json={}, headers=headers(senior)).status_code == 403
    assert client.post(employee_endpoint, json={}, headers=headers(manager)).status_code == 200
    manager_request = create(manager)
    assert client.post(
        f"/api/v1/leaves/{manager_request.json()['id']}/approve",
        json={},
        headers=headers(senior),
    ).status_code == 200
    medical = create(employee, leave_type="MEDICAL")
    medical_endpoint = f"/api/v1/leaves/{medical.json()['id']}"
    before = client.get(medical_endpoint, headers=headers(manager)).json()
    assert client.post(f"{medical_endpoint}/approve", json={}, headers=headers(manager)).status_code == 409
    assert client.post(f"{medical_endpoint}/reject", json={}, headers=headers(manager)).status_code == 409
    after = client.get(medical_endpoint, headers=headers(manager)).json()
    assert after["decided_by_id"] is None
    assert after["decision_source"] == "AUTOMATIC_POLICY"
    assert after["decided_at"] == before["decided_at"]


def test_terminal_state_and_atomic_compare_and_set_protect_decisions():
    _, manager, employee, _ = setup()
    request = create(employee)
    approve = f"/api/v1/leaves/{request.json()['id']}/approve"
    reject = f"/api/v1/leaves/{request.json()['id']}/reject"
    assert client.post(approve, json={}, headers=headers(manager)).status_code == 200
    assert client.post(approve, json={}, headers=headers(manager)).status_code == 409
    assert client.post(reject, json={}, headers=headers(manager)).status_code == 409
    db = Session()
    stored = db.get(LeaveRequest, UUID(request.json()["id"]))
    assert stored.status is LeaveStatus.APPROVED
    db.close()
    second = create(employee)
    first_session = Session()
    second_session = Session()
    first_snapshot = first_session.get(LeaveRequest, UUID(second.json()["id"]))
    second_snapshot = second_session.get(LeaveRequest, UUID(second.json()["id"]))
    first_manager = first_session.get(Employee, manager.id)
    second_manager = second_session.get(Employee, manager.id)
    assert apply_manager_decision(
        first_session, first_snapshot, first_manager, LeaveStatus.REJECTED, None
    )
    first_session.commit()
    assert not apply_manager_decision(
        second_session, second_snapshot, second_manager, LeaveStatus.APPROVED, None
    )
    first_session.close()
    second_session.close()


def test_decision_not_found_and_malformed_id_are_safe():
    _, manager, _, _ = setup()
    assert client.post("/api/v1/leaves/not-a-uuid/approve", json={}, headers=headers(manager)).status_code == 404
    assert client.post(
        "/api/v1/leaves/00000000-0000-0000-0000-000000000000/reject",
        json={},
        headers=headers(manager),
    ).status_code == 404


def test_leave_submission_notifies_only_the_direct_manager():
    admin, manager, employee, other = setup()
    unrelated_manager = make_employee("OTHER_MANAGER", Role.MANAGER)
    for leave_type, overrides in (
        ("CASUAL", {}),
        ("EMERGENCY", {}),
        (
            "DAY_OFF",
            {
                "start_date": "2026-10-03",
                "end_date": "2026-10-03",
                "duration": "HALF_DAY",
                "half_day_period": "MORNING",
            },
        ),
    ):
        response = create(employee, leave_type=leave_type, **overrides)
        assert response.status_code == 201
        assert response.json()["manager_notification_delivered"] is True
    manager_notifications = notifications_for(manager)
    assert len(manager_notifications) == 3
    assert all(item.category is NotificationCategory.LEAVE for item in manager_notifications)
    assert all("approval required" in item.title.lower() for item in manager_notifications)
    assert notifications_for(unrelated_manager) == []
    assert notifications_for(admin) == []
    assert notifications_for(other) == []


def test_medical_is_informational_and_no_manager_fallback_is_created():
    admin, manager, employee, other = setup()
    medical = create(employee, leave_type="MEDICAL")
    assert medical.status_code == 201
    assert medical.json()["status"] == "APPROVED"
    assert medical.json()["manager_notification_delivered"] is True
    notifications = notifications_for(manager)
    assert len(notifications) == 1
    assert "automatically approved" in notifications[0].message.lower()
    assert "approval required" not in notifications[0].title.lower()
    assert medical.json()["decided_by_id"] is None
    no_manager = create(other)
    assert no_manager.status_code == 201
    assert no_manager.json()["manager_notification_delivered"] is False
    assert notifications_for(admin) == []
    assert len(notifications_for(manager)) == 1


def test_successful_decisions_notify_requester_and_failures_do_not():
    _, manager, employee, other = setup()
    request = create(employee)
    approve = f"/api/v1/leaves/{request.json()['id']}/approve"
    assert client.post(approve, json={}, headers=headers(other)).status_code == 403
    assert notifications_for(employee) == []
    assert client.post(approve, json={}, headers=headers(manager)).status_code == 200
    notifications = notifications_for(employee)
    assert len(notifications) == 1
    assert "approved" in notifications[0].title.lower()
    assert client.post(approve, json={}, headers=headers(manager)).status_code == 409
    assert len(notifications_for(employee)) == 1
    second = create(employee, leave_type="EMERGENCY")
    reject = f"/api/v1/leaves/{second.json()['id']}/reject"
    assert client.post(
        reject,
        json={"decision_note": "Coverage needed."},
        headers=headers(manager),
    ).status_code == 200
    notifications = notifications_for(employee)
    assert len(notifications) == 2
    assert "rejected" in notifications[-1].title.lower()
    assert "Coverage needed." in notifications[-1].message


def test_inbox_is_jwt_private_and_read_operations_are_scoped_and_idempotent():
    admin, manager, employee, other = setup()
    other.manager_id = manager.id
    db = Session()
    db.merge(other)
    db.commit()
    db.close()
    first = create(employee)
    second = create(other)
    first_approve = f"/api/v1/leaves/{first.json()['id']}/approve"
    second_approve = f"/api/v1/leaves/{second.json()['id']}/approve"
    assert client.post(first_approve, json={}, headers=headers(manager)).status_code == 200
    assert client.post(second_approve, json={}, headers=headers(manager)).status_code == 200
    employee_inbox = client.get("/api/v1/notifications", headers=headers(employee)).json()
    other_inbox = client.get("/api/v1/notifications", headers=headers(other)).json()
    manager_inbox = client.get("/api/v1/notifications", headers=headers(manager)).json()
    admin_inbox = client.get("/api/v1/notifications", headers=headers(admin)).json()
    assert len(employee_inbox) == len(other_inbox) == 1
    assert employee_inbox[0]["id"] != other_inbox[0]["id"]
    assert len(manager_inbox) == 2
    assert admin_inbox == []
    assert client.get("/api/v1/notifications/unread-count", headers=headers(employee)).json() == {"unread_count": 1}
    notification_id = employee_inbox[0]["id"]
    assert client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=headers(other)
    ).status_code == 404
    first_read = client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=headers(employee)
    )
    assert first_read.status_code == 200 and first_read.json()["is_read"] is True
    assert client.post(
        f"/api/v1/notifications/{notification_id}/read", headers=headers(employee)
    ).status_code == 200
    assert client.post("/api/v1/notifications/read-all", headers=headers(manager)).json() == {"updated_count": 2}
    assert client.get("/api/v1/notifications/unread-count", headers=headers(other)).json() == {"unread_count": 1}
