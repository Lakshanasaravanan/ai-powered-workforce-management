from datetime import date
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.calendar import CalendarEvent
from app.models.employee import Employee, Role
from app.models.leave import LeaveDuration, LeaveRequest, LeaveStatus, LeaveType


engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Session = sessionmaker(engine)
client = TestClient(app)


def db_override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
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


def auth(employee: Employee) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(str(employee.id))}"}


def setup():
    admin = make_employee("ADMIN", Role.ADMIN)
    manager = make_employee("MANAGER", Role.MANAGER)
    employee = make_employee("EMPLOYEE", manager_id=manager.id)
    other = make_employee("OTHER")
    return admin, manager, employee, other


def event_body(**overrides):
    body = {
        "title": "Planning session",
        "description": "Quarterly planning",
        "event_type": "MEETING",
        "start_at": "2025-04-02T09:00",
        "end_at": "2025-04-02T10:00",
        "all_day": False,
        "location": "Room A",
    }
    body.update(overrides)
    return body


def create_event(actor: Employee, **overrides):
    return client.post("/api/v1/calendar/events", json=event_body(**overrides), headers=auth(actor))


def add_leave(employee: Employee, status: LeaveStatus, start: date, end: date) -> LeaveRequest:
    db = Session()
    leave = LeaveRequest(
        employee_id=employee.id,
        leave_type=LeaveType.CASUAL,
        status=status,
        start_date=start,
        end_date=end,
        duration=LeaveDuration.FULL_DAY,
        half_day_period=None,
        reason="Test leave",
        approval_required=status is LeaveStatus.PENDING,
    )
    db.add(leave)
    db.commit()
    db.refresh(leave)
    db.close()
    return leave


def feed(actor: Employee, start="2025-04-01", end="2025-04-30"):
    return client.get(f"/api/v1/calendar/feed?start={start}&end={end}", headers=auth(actor))


def test_calendar_authentication_crud_validation_and_creator_identity():
    _, manager, employee, _ = setup()
    assert client.get("/api/v1/calendar/feed?start=2025-04-01&end=2025-04-30").status_code == 401
    assert client.post("/api/v1/calendar/events", json=event_body()).status_code == 401
    created = create_event(manager, created_by=str(employee.id))
    assert created.status_code == 422
    created = create_event(manager)
    assert created.status_code == 200
    event_id = created.json()["id"]
    assert client.get(f"/api/v1/calendar/events/{event_id}").status_code == 401
    assert client.patch(f"/api/v1/calendar/events/{event_id}", json=event_body()).status_code == 401
    assert client.delete(f"/api/v1/calendar/events/{event_id}").status_code == 401
    assert client.get(f"/api/v1/calendar/events/{event_id}", headers=auth(employee)).status_code == 200
    db = Session()
    assert db.get(CalendarEvent, UUID(event_id)).created_by == manager.id
    db.close()
    assert client.patch(f"/api/v1/calendar/events/{event_id}", json=event_body(title="Changed"), headers=auth(employee)).status_code == 403
    assert client.delete(f"/api/v1/calendar/events/{event_id}", headers=auth(employee)).status_code == 403
    updated = client.patch(f"/api/v1/calendar/events/{event_id}", json=event_body(title="Changed"), headers=auth(manager))
    assert updated.status_code == 200 and updated.json()["title"] == "Changed"
    assert client.post("/api/v1/calendar/events", json=event_body(start_at="2025-04-03T10:00", end_at="2025-04-03T09:00"), headers=auth(manager)).status_code == 422
    assert client.post("/api/v1/calendar/events", json={"title": "Only title"}, headers=auth(manager)).status_code == 422
    assert client.get("/api/v1/calendar/feed?start=2025-04-30&end=2025-04-01", headers=auth(employee)).status_code == 422
    assert client.delete(f"/api/v1/calendar/events/{event_id}", headers=auth(manager)).status_code == 200
    assert client.get(f"/api/v1/calendar/events/{event_id}", headers=auth(manager)).status_code == 404


def test_calendar_event_date_range_and_multiday_intersection():
    _, manager, employee, _ = setup()
    intersecting = create_event(manager, title="Multi day", start_at="2025-04-02T09:00", end_at="2025-04-04T17:00")
    outside = create_event(manager, title="Outside", start_at="2025-05-01T09:00", end_at="2025-05-01T10:00")
    assert intersecting.status_code == outside.status_code == 200
    result = feed(employee, "2025-04-03", "2025-04-03")
    assert result.status_code == 200
    ids = {item["id"] for item in result.json()}
    assert intersecting.json()["id"] in ids
    assert outside.json()["id"] not in ids


def test_leave_projection_status_visibility_privacy_and_date_range():
    admin, manager, employee, other = setup()
    approved = add_leave(employee, LeaveStatus.APPROVED, date(2025, 4, 2), date(2025, 4, 4))
    add_leave(employee, LeaveStatus.PENDING, date(2025, 4, 8), date(2025, 4, 8))
    add_leave(employee, LeaveStatus.REJECTED, date(2025, 4, 9), date(2025, 4, 9))
    own = feed(employee, "2025-04-03", "2025-04-03")
    assert own.status_code == 200
    projected = [item for item in own.json() if item["kind"] == "LEAVE"]
    assert [item["id"] for item in projected] == [str(approved.id)]
    assert projected[0]["all_day"] is True and projected[0]["title"] == "Approved leave"
    db = Session()
    assert db.query(CalendarEvent).count() == 0
    db.close()
    assert str(approved.id) in {item["id"] for item in feed(manager, "2025-04-03", "2025-04-03").json()}
    assert str(approved.id) not in {item["id"] for item in feed(other, "2025-04-03", "2025-04-03").json()}
    assert str(approved.id) not in {item["id"] for item in feed(admin, "2025-04-03", "2025-04-03").json()}
    assert str(approved.id) not in {item["id"] for item in feed(employee, "2025-05-01", "2025-05-01").json()}


def test_private_leave_projections_are_not_event_resources():
    _, _, employee, _ = setup()
    leave = add_leave(employee, LeaveStatus.APPROVED, date(2025, 4, 10), date(2025, 4, 10))
    response = client.get(f"/api/v1/calendar/events/{leave.id}", headers=auth(employee))
    assert response.status_code == 404
