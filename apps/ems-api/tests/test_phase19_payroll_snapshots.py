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
from app.models.audit import AuditEvent
from app.models.employee import CompensationConfiguration, Employee, Role
from app.models.payroll import PayrollSnapshot
from app.services.payroll import working_dates

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine)
client = TestClient(app)


def override():
    db = Session()
    try: yield db
    finally: db.close()


@pytest.fixture(autouse=True)
def isolated():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine); app.dependency_overrides[get_db] = override
    yield
    app.dependency_overrides.pop(get_db, None)


def employee(code, role=Role.EMPLOYEE):
    db=Session(); item=Employee(employee_code=code, full_name=code, company_email=f"{code}@infotech.local", role=role, designation="Engineer", department="Engineering", password_hash=hash_password("test-password"), onboarding_completed=True, is_active=True); db.add(item); db.commit(); db.refresh(item); db.expunge(item); db.close(); return item


def auth(item): return {"Authorization": f"Bearer {token(str(item.id))}"}


def ready_month(subject, year=2025, month=4):
    db=Session(); admin=employee("PAYADMIN", Role.ADMIN)
    db.add(CompensationConfiguration(employee_id=subject.id, monthly_salary=Decimal("2400.00"), overtime_hourly_rate=Decimal("100.00"), late_deduction_amount=Decimal("50.00"), effective_from=date(year, month, 1), created_by=admin.id)); db.commit()
    for day in working_dates(db, year, month): db.add(AttendanceRecord(employee_id=subject.id, attendance_date=day, status=AttendanceStatus.PRESENT, source=AttendanceSource.FACE, regular_check_in_at=datetime(day.year, day.month, day.day, 9), regular_check_out_at=datetime(day.year, day.month, day.day, 17)))
    db.commit(); db.close(); return admin


def endpoint(subject, suffix=""): return f"/api/v1/payroll/{subject.id}{suffix}?year=2025&month=4"


def test_finalize_snapshot_round_trip_audit_history_and_immutability():
    subject=employee("PAYEMP"); admin=ready_month(subject)
    preview=client.get(endpoint(subject),headers=auth(admin)).json()
    finalized=client.post(endpoint(subject,"/finalize"),headers=auth(admin)); assert finalized.status_code==200
    body=finalized.json(); assert body["payable_salary"]==preview["payable_salary_preview"] and body["daily_breakdown"][0]["date"] == "2025-04-01"
    db=Session(); snapshot=db.query(PayrollSnapshot).one(); audit=db.query(AuditEvent).filter_by(operation="finalize_payroll").one(); assert snapshot.finalized_by_admin_id==admin.id and audit.actor_employee_id==admin.id and audit.target_id==snapshot.id; first=body["payable_salary"]
    record=db.query(AttendanceRecord).filter_by(employee_id=subject.id,attendance_date=date(2025,4,1)).one(); record.status=AttendanceStatus.ABSENT; db.commit(); db.close()
    assert client.get(endpoint(subject),headers=auth(admin)).json()["payable_salary_preview"] != first
    read=client.get(endpoint(subject,"/finalized"),headers=auth(admin)); history=client.get(f"/api/v1/payroll/{subject.id}/finalized-history",headers=auth(admin))
    assert read.status_code==200 and read.json()["payable_salary"]==first and len(history.json())==1
    assert client.post(endpoint(subject,"/finalize"),headers=auth(admin)).status_code==409


def test_finalization_blocks_missing_and_open_overtime_without_successful_audit():
    subject=employee("PAYEMP"); admin=ready_month(subject)
    db=Session(); db.delete(db.query(AttendanceRecord).filter_by(employee_id=subject.id,attendance_date=date(2025,4,1)).one()); db.commit(); db.close()
    assert client.get(endpoint(subject),headers=auth(admin)).status_code==200
    assert client.post(endpoint(subject,"/finalize"),headers=auth(admin)).status_code==422
    db=Session(); assert db.query(PayrollSnapshot).count()==0 and db.query(AuditEvent).filter_by(operation="finalize_payroll").count()==0
    db.add(AttendanceRecord(employee_id=subject.id,attendance_date=date(2025,4,1),status=AttendanceStatus.PRESENT,source=AttendanceSource.FACE,regular_check_in_at=datetime(2025,4,1,9),regular_check_out_at=datetime(2025,4,1,17))); db.add(OvertimeSession(employee_id=subject.id,attendance_date=date(2025,4,1),check_in_at=datetime(2025,4,1,17),check_out_at=None)); db.commit(); db.close()
    assert client.post(endpoint(subject,"/finalize"),headers=auth(admin)).status_code==422


def test_finalization_and_finalized_reads_are_admin_only_and_admin_subject_is_rejected():
    subject=employee("PAYEMP"); admin=ready_month(subject); manager=employee("PAYMAN",Role.MANAGER); other=employee("PAYOTHER")
    url=endpoint(subject,"/finalize")
    assert client.post(url).status_code==401 and client.post(url,headers=auth(subject)).status_code==403 and client.post(url,headers=auth(manager)).status_code==403
    assert client.post(url,headers=auth(admin)).status_code==200
    read=endpoint(subject,"/finalized")
    assert client.get(read,headers=auth(subject)).status_code==403 and client.get(read,headers=auth(manager)).status_code==403 and client.get(read,headers=auth(admin)).status_code==200
    assert client.post(endpoint(admin,"/finalize"),headers=auth(admin)).status_code==422


def test_admin_can_finalize_manager_and_current_or_future_periods_are_rejected():
    manager = employee("PAYMAN", Role.MANAGER); admin = ready_month(manager)
    assert client.post(endpoint(manager, "/finalize"), headers=auth(admin)).status_code == 200
    current = date.today()
    assert client.post(f"/api/v1/payroll/{manager.id}/finalize?year={current.year}&month={current.month}", headers=auth(admin)).status_code == 422
    future_year, future_month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
    assert client.post(f"/api/v1/payroll/{manager.id}/finalize?year={future_year}&month={future_month}", headers=auth(admin)).status_code == 422
