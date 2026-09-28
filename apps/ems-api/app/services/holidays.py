from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.models.holiday import CompanyHoliday


def is_default_company_holiday(day: date) -> bool:
    if day.weekday() == 6:
        return True
    if day.weekday() != 5:
        return False
    occurrence = (day.day - 1) // 7 + 1
    return occurrence in (2, 4)


def default_holiday_name(day: date) -> str:
    if day.weekday() == 6:
        return "Sunday"
    occurrence = (day.day - 1) // 7 + 1
    return f"{occurrence}{'th' if occurrence == 4 else 'nd'} Saturday"


def is_company_holiday(db: Session, day: date) -> bool:
    return is_default_company_holiday(day) or db.query(CompanyHoliday.id).filter_by(holiday_date=day).first() is not None


def is_working_day(db: Session, day: date) -> bool:
    return not is_company_holiday(db, day)


def holidays_in_range(db: Session, start: date, end: date) -> list[dict]:
    custom = {item.holiday_date: item for item in db.query(CompanyHoliday).filter(CompanyHoliday.holiday_date >= start, CompanyHoliday.holiday_date <= end)}
    rows: list[dict] = []
    cursor = start
    while cursor <= end:
        if is_default_company_holiday(cursor):
            rows.append({"id": f"default-{cursor.isoformat()}", "holiday_date": cursor.isoformat(), "name": default_holiday_name(cursor), "is_default": True, "deletable": False})
        elif cursor in custom:
            item = custom[cursor]
            rows.append({"id": str(item.id), "holiday_date": cursor.isoformat(), "name": item.name, "is_default": False, "deletable": True})
        cursor += timedelta(days=1)
    return rows
