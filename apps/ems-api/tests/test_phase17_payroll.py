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


def add_compensation(employee: Employee, start: date, monthly: str = "1000.00", end: date | None = None, overtime: str = "10.00", late: str = "5.00"):
    db = Session()
    db.add(CompensationConfiguration(employee_id=employee.id, monthly_salary=Decimal(monthly),
           overtime_hourly_rate=Decimal(overtime), late_deduction_amount=Decimal(late),
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


def test_phase18_deficit_recovery_paid_overtime_deductions_and_preview_totals():
    admin = add_employee("PAYADMIN", Role.ADMIN); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1), "2400.00", overtime="200.00", late="50.00")
    db = Session()
    def present(day, start_hour, start_minute=0, end_hour=17):
        db.add(AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, day), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, day, start_hour, start_minute), regular_check_out_at=datetime(2025, 4, day, end_hour)))
    def overtime(day, end_hour):
        db.add(OvertimeSession(employee_id=employee.id, attendance_date=date(2025, 4, day), check_in_at=datetime(2025, 4, day, 17), check_out_at=datetime(2025, 4, day, end_hour)))
    present(1, 9); present(2, 9, 15); present(3, 10); present(4, 10); overtime(4, 18)
    present(5, 9); overtime(5, 18); present(7, 10); overtime(7, 20)
    present(8, 10, end_hour=16); overtime(8, 18); present(9, 9, 15); overtime(9, 18)
    db.add(AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 10), status=AttendanceStatus.LEAVE, source=AttendanceSource.APPROVED_LEAVE))
    db.add(AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 11), status=AttendanceStatus.ABSENT, source=AttendanceSource.ADMIN_OVERRIDE))
    db.commit(); db.close()
    response = client.get(f"/api/v1/payroll/{employee.id}?year=2025&month=4", headers=auth(admin))
    assert response.status_code == 200
    body = response.json(); days = {item["date"]: item for item in body["daily_breakdown"]}
    assert days["2025-04-01"]["regular_qualifying_minutes"] == 480 and days["2025-04-01"]["paid_overtime_minutes"] == 0
    assert days["2025-04-02"]["arrival_delay_minutes"] == 15 and days["2025-04-02"]["late_deduction_amount"] == "0.00"
    assert days["2025-04-03"]["regular_deficit_minutes"] == 60 and days["2025-04-03"]["late_deduction_amount"] == "50.00"
    assert (days["2025-04-04"]["deficit_recovery_minutes"], days["2025-04-04"]["paid_overtime_minutes"], days["2025-04-04"]["late_deduction_amount"]) == (60, 0, "0.00")
    assert (days["2025-04-05"]["raw_overtime_minutes"], days["2025-04-05"]["paid_overtime_minutes"], days["2025-04-05"]["overtime_pay"]) == (60, 60, "200.00")
    assert (days["2025-04-07"]["deficit_recovery_minutes"], days["2025-04-07"]["paid_overtime_minutes"]) == (60, 120)
    assert (days["2025-04-08"]["regular_deficit_minutes"], days["2025-04-08"]["unrecovered_deficit_minutes"], days["2025-04-08"]["late_deduction_amount"]) == (120, 60, "50.00")
    assert (days["2025-04-09"]["deficit_recovery_minutes"], days["2025-04-09"]["paid_overtime_minutes"], days["2025-04-09"]["overtime_pay"]) == (15, 45, "150.00")
    assert days["2025-04-10"]["classification"] == "PAID_LEAVE" and days["2025-04-10"]["regular_deficit_minutes"] == 0
    assert days["2025-04-11"]["absence_deduction"] == "100.00" and days["2025-04-11"]["late_deduction_amount"] == "0.00"
    assert body["missing_attendance_days"] > 0 and body["total_regular_deficit_minutes"] == 330
    assert body["total_deficit_recovery_minutes"] == 195 and body["total_paid_overtime_minutes"] == 225
    assert body["total_absence_deduction"] == "100.00" and body["total_late_deduction"] == "100.00"
    assert body["total_overtime_pay"] == "750.00" and body["regular_salary_after_absence"] == "2300.00" and body["payable_salary_preview"] == "2950.00"


def test_qualifying_regular_window_caps_early_and_after_hours():
    employee = add_employee("PAYEMP")
    db = Session()
    early = AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 1), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 1, 8, 45), regular_check_out_at=datetime(2025, 4, 1, 17))
    after = AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 2), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 2, 9), regular_check_out_at=datetime(2025, 4, 2, 18))
    early_departure = AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 3), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 3, 9), regular_check_out_at=datetime(2025, 4, 3, 16))
    from app.services.payroll import qualifying_regular_minutes
    assert qualifying_regular_minutes(early) == (480, 0) and qualifying_regular_minutes(after) == (480, 0) and qualifying_regular_minutes(early_departure) == (420, 0)
    db.close()


def test_effective_dated_salary_overtime_and_late_rates_apply_to_each_day():
    admin = add_employee("PAYADMIN", Role.ADMIN); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1), "2400.00", date(2025, 4, 15), overtime="60.00", late="10.00")
    add_compensation(employee, date(2025, 4, 16), "4800.00", overtime="120.00", late="20.00")
    db = Session()
    db.add_all([
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 1), status=AttendanceStatus.ABSENT, source=AttendanceSource.ADMIN_OVERRIDE),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 16), status=AttendanceStatus.ABSENT, source=AttendanceSource.ADMIN_OVERRIDE),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 2), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 2, 10), regular_check_out_at=datetime(2025, 4, 2, 17)),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 17), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 17, 9), regular_check_out_at=datetime(2025, 4, 17, 17)),
        OvertimeSession(employee_id=employee.id, attendance_date=date(2025, 4, 17), check_in_at=datetime(2025, 4, 17, 17), check_out_at=datetime(2025, 4, 17, 18)),
    ])
    db.commit(); db.close()
    body = client.get(f"/api/v1/payroll/{employee.id}?year=2025&month=4", headers=auth(admin)).json()
    days = {item["date"]: item for item in body["daily_breakdown"]}
    assert days["2025-04-01"]["absence_deduction"] == "100.00" and days["2025-04-16"]["absence_deduction"] == "200.00"
    assert days["2025-04-02"]["late_deduction_amount"] == "10.00" and days["2025-04-17"]["overtime_pay"] == "120.00"


def test_sub_sixty_minute_unrecovered_deficits_never_apply_late_deduction():
    admin = add_employee("PAYADMIN", Role.ADMIN); employee = add_employee("PAYEMP")
    add_compensation(employee, date(2025, 4, 1), "2400.00", overtime="100.00", late="50.00")
    db = Session()
    db.add_all([
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 1), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 1, 9, 1), regular_check_out_at=datetime(2025, 4, 1, 17)),
        AttendanceRecord(employee_id=employee.id, attendance_date=date(2025, 4, 2), status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(2025, 4, 2, 9, 59), regular_check_out_at=datetime(2025, 4, 2, 17)),
    ])
    db.commit(); db.close()
    body = client.get(f"/api/v1/payroll/{employee.id}?year=2025&month=4", headers=auth(admin)).json()
    days = {item["date"]: item for item in body["daily_breakdown"]}
    assert days["2025-04-01"]["unrecovered_deficit_minutes"] == 1 and days["2025-04-02"]["unrecovered_deficit_minutes"] == 59
    assert days["2025-04-01"]["late_deduction_amount"] == "0.00" and days["2025-04-02"]["late_deduction_amount"] == "0.00"
