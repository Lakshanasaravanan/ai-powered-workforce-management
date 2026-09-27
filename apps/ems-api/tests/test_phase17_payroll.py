from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.attendance import AttendanceRecord, AttendanceSource, AttendanceStatus, OvertimeSession
from app.models.employee import CompensationConfiguration, Employee, Role
from app.models.holiday import CompanyHoliday
from app.services.payroll import money, working_dates


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine)
client = TestClient(app)


def override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def isolated_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.pop(get_db, None)


def add_employee(code: str, role: Role = Role.EMPLOYEE) -> Employee:
    db = Session()
    row = Employee(employee_code=code, full_name=code, company_email=f"{code}@infotech.local", role=role,
                   designation="Engineer", department="Engineering", password_hash=hash_password("test-password"),
                   onboarding_completed=True, is_active=True)
    db.add(row); db.commit(); db.refresh(row); db.expunge(row); db.close()
    return row


def auth(user: Employee) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(str(user.id))}"}


def add_compensation(employee: Employee, start: date, monthly: str = "1000.00", end: date | None = None):
    db = Session()
    db.add(CompensationConfiguration(employee_id=employee.id, monthly_salary=Decimal(monthly),
           overtime_hourly_rate=Decimal("10.00"), late_deduction_amount=Decimal("5.00"),
           effective_from=start, effective_to=end, created_by=employee.id))
    db.commit(); db.close()


def test_working_calendar_and_decimal_rounding_use_authoritative_holidays():
    admin = add_employee("PAYADMIN", Role.ADMIN)
    db = Session(); db.add(CompanyHoliday(holiday_date=date(2025, 4, 14), name="Company day", created_by=admin.id)); db.commit()
    days = working_dates(db, 2025, 4); db.close()
    assert date(2025, 4, 5) in days and date(2025, 4, 19) in days
    assert date(2025, 4, 6) not in days and date(2025, 4, 12) not in days and date(2025, 4, 26) not in days
    assert date(2025, 4, 14) not in days
    assert len(days) == 23 and money(Decimal("1000") / Decimal(len(days))) == Decimal("43.48")
    db = Session(); may_days = working_dates(db, 2025, 5); db.close()
    assert date(2025, 5, 3) in may_days and date(2025, 5, 17) in may_days and date(2025, 5, 31) in may_days


def test_admin_preview_classifies_attendance_and_closed_overtime_only():
    admin = add_employee("PAYADMIN", Role.ADMIN); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1))
    db = Session()
    db.add_all([
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 1), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 1, 9), regular_check_out_at=datetime(2025, 4, 1, 17)),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 2), status=AttendanceStatus.LEAVE, source=AttendanceSource.APPROVED_LEAVE),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 3), status=AttendanceStatus.ABSENT, source=AttendanceSource.ADMIN_OVERRIDE),
        OvertimeSession(employee_id=employee.id, attendance_date=date(2025, 4, 1), check_in_at=datetime(2025, 4, 1, 17), check_out_at=datetime(2025, 4, 1, 19)),
        OvertimeSession(employee_id=employee.id, attendance_date=date(2025, 4, 4), check_in_at=datetime(2025, 4, 4, 17), check_out_at=None),
    ])
    db.commit(); db.close()
    response = client.get(f"/api/v1/payroll/{employee.id}?year=2025&month=4", headers=auth(admin))
    assert response.status_code == 200
    body = response.json()
    assert body["present_days"] == 1 and body["paid_leave_days"] == 1 and body["explicit_absent_days"] == 1
    assert body["missing_attendance_days"] == body["working_days"] - 3
    assert body["regular_worked_minutes"] == 480 and body["raw_overtime_minutes"] == 120 and body["open_overtime_sessions"] == 1
    assert body["monthly_salary"] == "1000.00" and body["derived_daily_rate"] == "41.67"


def test_effective_compensation_history_splits_month_and_missing_configuration_is_clear():
    admin = add_employee("PAYADMIN", Role.ADMIN); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1), "1000.00", date(2025, 4, 15)); add_compensation(employee, date(2025, 4, 16), "2000.00")
    response = client.get(f"/api/v1/payroll/{employee.id}?year=2025&month=4", headers=auth(admin))
    assert response.status_code == 200
    periods = response.json()["compensation_periods"]
    assert len(periods) == 2 and {item["monthly_salary"] for item in periods} == {"1000.00", "2000.00"}
    missing = add_employee("PAYNOCOMP")
    response = client.get(f"/api/v1/payroll/{missing.id}?year=2025&month=4", headers=auth(admin))
    assert response.status_code == 422 and "compensation" in response.json()["detail"].lower()


def test_payroll_is_admin_only_and_administrators_are_not_subjects():
    admin = add_employee("PAYADMIN", Role.ADMIN); manager = add_employee("PAYMANAGER", Role.MANAGER); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1)); add_compensation(manager, date(2025, 4, 1))
    endpoint = f"/api/v1/payroll/{employee.id}?year=2025&month=4"
    assert client.get(endpoint).status_code == 401
    assert client.get(endpoint, headers=auth(employee)).status_code == 403
    assert client.get(endpoint, headers=auth(manager)).status_code == 403
    assert client.get(f"/api/v1/payroll/{manager.id}?year=2025&month=4", headers=auth(admin)).status_code == 200
    assert client.get(f"/api/v1/payroll/{admin.id}?year=2025&month=4", headers=auth(admin)).status_code == 422
