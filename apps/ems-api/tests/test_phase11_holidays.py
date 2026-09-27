from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.calendar import router
from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.employee import Employee, Role
from app.models.holiday import CompanyHoliday
from app.services.holidays import is_company_holiday, is_working_day


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
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
    previous_override = app.dependency_overrides.get(get_db)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = db_override
    yield
    if previous_override is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_override


def make_employee(code: str, role: Role) -> Employee:
    db = Session()
    item = Employee(employee_code=code, full_name=code, company_email=f"{code}@infotech.local", role=role, designation="Engineer", department="Engineering", password_hash=hash_password("test-password"), onboarding_completed=True, is_active=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    db.close()
    return item


def auth(employee: Employee) -> dict[str, str]:
    return {"Authorization": f"Bearer {token(str(employee.id))}"}


def setup():
    return make_employee("ADMIN", Role.ADMIN), make_employee("MANAGER", Role.MANAGER), make_employee("EMPLOYEE", Role.EMPLOYEE)


def holidays(actor: Employee, start="2025-03-01", end="2025-03-31"):
    return client.get(f"/api/v1/calendar/holidays?start={start}&end={end}", headers=auth(actor))


def test_default_working_day_rules_are_deterministic_across_months():
    db = Session()
    assert is_company_holiday(db, date(2025, 3, 2))  # Sunday
    assert is_company_holiday(db, date(2025, 3, 8))  # second Saturday
    assert is_company_holiday(db, date(2025, 3, 22))  # fourth Saturday
    assert not is_company_holiday(db, date(2025, 3, 1))  # first Saturday
    assert not is_company_holiday(db, date(2025, 3, 15))  # third Saturday
    assert not is_company_holiday(db, date(2025, 3, 29))  # fifth Saturday
    assert is_working_day(db, date(2025, 4, 1))
    assert is_company_holiday(db, date(2026, 2, 14))  # second Saturday in a different month/year
    db.close()


def test_holiday_reads_are_authenticated_and_include_defaults_in_calendar_feed():
    admin, manager, employee = setup()
    assert client.get("/api/v1/calendar/holidays?start=2025-03-01&end=2025-03-31").status_code == 401
    for actor in (admin, manager, employee):
        response = holidays(actor)
        assert response.status_code == 200
        values = response.json()
        assert any(item["holiday_date"] == "2025-03-02" and item["is_default"] for item in values)
    feed = client.get("/api/v1/calendar/feed?start=2025-03-08&end=2025-03-08", headers=auth(employee))
    assert feed.status_code == 200
    item = next(row for row in feed.json() if row["kind"] == "HOLIDAY")
    assert item["all_day"] is True and item["is_default"] is True and item["deletable"] is False


def test_admin_custom_holiday_lifecycle_authorization_and_uniqueness():
    admin, manager, employee = setup()
    body = {"holiday_date": "2025-03-10", "name": "Founders Day"}
    assert client.post("/api/v1/calendar/holidays", json=body, headers=auth(employee)).status_code == 403
    assert client.post("/api/v1/calendar/holidays", json=body, headers=auth(manager)).status_code == 403
    created = client.post("/api/v1/calendar/holidays", json=body, headers=auth(admin))
    assert created.status_code == 200 and created.json()["deletable"] is True
    feed = client.get("/api/v1/calendar/feed?start=2025-03-10&end=2025-03-10", headers=auth(employee))
    assert any(item["kind"] == "HOLIDAY" and item["title"] == "Founders Day" and item["deletable"] for item in feed.json())
    assert client.post("/api/v1/calendar/holidays", json=body, headers=auth(admin)).status_code == 409
    assert client.post("/api/v1/calendar/holidays", json={"holiday_date": "2025-03-08", "name": "Duplicate default"}, headers=auth(admin)).status_code == 422
    holiday_id = created.json()["id"]
    assert client.delete(f"/api/v1/calendar/holidays/{holiday_id}", headers=auth(employee)).status_code == 403
    assert client.delete(f"/api/v1/calendar/holidays/{holiday_id}", headers=auth(manager)).status_code == 403
    assert client.delete("/api/v1/calendar/holidays/default-2025-03-08", headers=auth(admin)).status_code == 422
    assert client.delete(f"/api/v1/calendar/holidays/{holiday_id}", headers=auth(admin)).status_code == 200
    db = Session()
    assert db.query(CompanyHoliday).count() == 0
    db.close()
