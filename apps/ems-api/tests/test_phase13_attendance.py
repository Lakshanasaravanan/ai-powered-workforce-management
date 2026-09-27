from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.attendance import AttendanceRecord, AttendanceSource, AttendanceStatus
from app.models.employee import Employee, Role
from app.models.holiday import CompanyHoliday
from app.models.leave import LeaveRequest, LeaveStatus, LeaveType, LeaveDuration


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine)
client = TestClient(app)


def db_override():
    db = Session()
    try: yield db
    finally: db.close()


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); app.dependency_overrides[get_db] = db_override
    yield
    app.dependency_overrides.pop(get_db, None)


def employee(code, role=Role.EMPLOYEE, manager_id=None):
    db = Session(); value = Employee(employee_code=code, full_name=code, company_email=f"{code}@infotech.local", role=role, designation="Engineer", department="Engineering", password_hash=hash_password("test-password"), onboarding_completed=True, is_active=True, manager_id=manager_id); db.add(value); db.commit(); db.refresh(value); db.close(); return value


def auth(value): return {"Authorization": f"Bearer {token(str(value.id))}"}


def setup():
    admin = employee("ADMIN", Role.ADMIN); manager = employee("MANAGER", Role.MANAGER); direct = employee("DIRECT", manager_id=manager.id); other_manager = employee("OTHER_MANAGER", Role.MANAGER); other = employee("OTHER", manager_id=other_manager.id); return admin, manager, direct, other_manager, other


def add_record(subject, day, status=AttendanceStatus.PRESENT, check_in=None, check_out=None, source=AttendanceSource.FACE):
    db = Session(); record = AttendanceRecord(employee_id=subject.id, attendance_date=day, status=status, regular_check_in_at=check_in, regular_check_out_at=check_out, source=source); db.add(record); db.commit(); db.refresh(record); db.close(); return record


def feed(path, actor, start="2025-04-01", end="2025-04-30"):
    return client.get(f"{path}?start={start}&end={end}", headers=auth(actor))


def test_attendance_model_unique_statuses_and_derived_display():
    _, _, direct, _, _ = setup()
    present = add_record(direct, date(2025, 4, 2), check_in=datetime(2025, 4, 2, 9, 0), check_out=datetime(2025, 4, 2, 17, 0))
    late = add_record(direct, date(2025, 4, 3), check_in=datetime(2025, 4, 3, 9, 15), check_out=datetime(2025, 4, 3, 17, 0))
    leave = add_record(direct, date(2025, 4, 4), AttendanceStatus.LEAVE, source=AttendanceSource.APPROVED_LEAVE)
    absent = add_record(direct, date(2025, 4, 5), AttendanceStatus.ABSENT)
    assert {present.status, late.status, leave.status, absent.status} == {AttendanceStatus.PRESENT, AttendanceStatus.LEAVE, AttendanceStatus.ABSENT}
    response = feed(f"/api/v1/attendance/employees/{direct.id}", direct)
    assert response.status_code == 200
    rows = {row["attendance_date"]: row for row in response.json()["records"]}
    assert rows["2025-04-02"]["late_minutes"] == 0 and rows["2025-04-02"]["worked_minutes"] == 480
    assert rows["2025-04-03"]["late_minutes"] == 15 and rows["2025-04-03"]["worked_minutes"] == 465
    assert rows["2025-04-04"]["leave_type"] is None and rows["2025-04-05"]["regular_check_out_at"] is None
    db = Session(); db.add(AttendanceRecord(employee_id=direct.id, attendance_date=date(2025, 4, 2), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE));
    with pytest.raises(IntegrityError): db.commit()
    db.rollback(); db.close()


def test_attendance_rbac_admin_exclusion_and_private_manager_scope():
    admin, manager, direct, other_manager, other = setup(); add_record(manager, date(2025, 4, 2)); add_record(direct, date(2025, 4, 2)); add_record(other, date(2025, 4, 2)); add_record(other_manager, date(2025, 4, 2))
    assert feed("/api/v1/attendance/me", direct).status_code == 200
    assert feed(f"/api/v1/attendance/employees/{manager.id}", direct).status_code == 403
    assert feed(f"/api/v1/attendance/employees/{other.id}", direct).status_code == 403
    assert feed("/api/v1/attendance/me", manager).status_code == 200
    assert feed(f"/api/v1/attendance/employees/{direct.id}", manager).status_code == 200
    assert feed(f"/api/v1/attendance/employees/{other.id}", manager).status_code == 403
    assert feed(f"/api/v1/attendance/employees/{other_manager.id}", manager).status_code == 403
    assert feed("/api/v1/attendance/me", admin).status_code == 403
    assert feed(f"/api/v1/attendance/employees/{direct.id}", admin).status_code == 200
    assert feed(f"/api/v1/attendance/employees/{manager.id}", admin).status_code == 200
    assert feed(f"/api/v1/attendance/employees/{admin.id}", admin).status_code == 422


def test_attendance_holidays_are_displayed_without_fake_records():
    _, _, direct, _, _ = setup()
    db = Session(); db.add(CompanyHoliday(holiday_date=date(2025, 4, 14), name="Company day", created_by=direct.id)); db.commit(); db.close()
    response = feed("/api/v1/attendance/me", direct, "2025-04-01", "2025-04-30")
    assert response.status_code == 200
    holidays = {row["date"]: row["name"] for row in response.json()["holidays"]}
    assert holidays["2025-04-06"] == "Sunday" and holidays["2025-04-12"] == "2nd Saturday" and holidays["2025-04-26"] == "4th Saturday" and holidays["2025-04-14"] == "Company day"
    assert response.json()["records"] == []
