from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, AttendanceStatus, OvertimeSession
from app.models.employee import CompensationConfiguration, Employee, Role
from app.services.attendance import regular_minutes
from app.services.holidays import is_working_day


MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 9999:
        raise HTTPException(422, "Invalid payroll month")
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def working_dates(db: Session, year: int, month: int) -> list[date]:
    start, end = month_bounds(year, month)
    return [date(year, month, day) for day in range(1, end.day + 1) if is_working_day(db, date(year, month, day))]


def _applicable_compensation(db: Session, employee_id, day: date) -> CompensationConfiguration | None:
    return (
        db.query(CompensationConfiguration)
        .filter(
            CompensationConfiguration.employee_id == employee_id,
            CompensationConfiguration.effective_from <= day,
            (CompensationConfiguration.effective_to.is_(None) | (CompensationConfiguration.effective_to >= day)),
        )
        .order_by(CompensationConfiguration.effective_from.desc())
        .first()
    )


def payroll_preview(db: Session, employee: Employee, year: int, month: int) -> dict:
    if employee.role == Role.ADMIN:
        raise HTTPException(422, "Administrators are not payroll attendance subjects")

    start, end = month_bounds(year, month)
    days = working_dates(db, year, month)
    configs_by_day: dict[date, CompensationConfiguration] = {}
    for day in days:
        config = _applicable_compensation(db, employee.id, day)
        if not config:
            raise HTTPException(422, "No compensation configuration covers every company working day in this payroll month")
        configs_by_day[day] = config

    records = {
        item.attendance_date: item
        for item in db.query(AttendanceRecord).filter(
            AttendanceRecord.employee_id == employee.id,
            AttendanceRecord.attendance_date >= start,
            AttendanceRecord.attendance_date <= end,
        )
    }
    present = paid_leave = absent = missing = regular_worked = incomplete_regular = 0
    for day in days:
        record = records.get(day)
        if not record:
            missing += 1
        elif record.status == AttendanceStatus.PRESENT:
            present += 1
            minutes = regular_minutes(record)
            if minutes is None:
                incomplete_regular += 1
            else:
                regular_worked += minutes
        elif record.status == AttendanceStatus.LEAVE:
            paid_leave += 1
        elif record.status == AttendanceStatus.ABSENT:
            absent += 1

    overtime = db.query(OvertimeSession).filter(
        OvertimeSession.employee_id == employee.id,
        OvertimeSession.attendance_date >= start,
        OvertimeSession.attendance_date <= end,
    ).all()
    raw_ot_minutes = sum(
        max(0, int((item.check_out_at - item.check_in_at).total_seconds() // 60))
        for item in overtime if item.check_out_at is not None
    )
    open_ot = sum(item.check_out_at is None for item in overtime)

    grouped: dict[object, list[date]] = defaultdict(list)
    for day, config in configs_by_day.items():
        grouped[config.id].append(day)
    periods = []
    prorated_total = Decimal("0")
    daily_rates = []
    for config_id, config_days in grouped.items():
        config = configs_by_day[config_days[0]]
        daily = Decimal(config.monthly_salary) / Decimal(len(days)) if days else Decimal("0")
        prorated = daily * Decimal(len(config_days))
        prorated_total += prorated
        daily_rates.extend([daily] * len(config_days))
        periods.append({
            "effective_from": max(start, config.effective_from).isoformat(),
            "effective_to": min(end, config.effective_to or end).isoformat(),
            "working_days": len(config_days),
            "monthly_salary": money(Decimal(config.monthly_salary)),
            "derived_daily_rate": money(daily),
            "prorated_salary_foundation": money(prorated),
            "overtime_hourly_rate": money(Decimal(config.overtime_hourly_rate)),
            "late_deduction_amount": money(Decimal(config.late_deduction_amount)),
        })
    periods.sort(key=lambda item: item["effective_from"])
    latest = configs_by_day[days[-1]] if days else _applicable_compensation(db, employee.id, start)
    if not latest:
        raise HTTPException(422, "No compensation configuration covers this payroll month")
    return {
        "employee_id": str(employee.id), "employee_code": employee.employee_code, "employee_name": employee.full_name,
        "year": year, "month": month, "working_days": len(days), "present_days": present, "paid_leave_days": paid_leave,
        "explicit_absent_days": absent, "missing_attendance_days": missing, "regular_worked_minutes": regular_worked,
        "regular_records_without_completed_checkout": incomplete_regular, "raw_overtime_minutes": raw_ot_minutes,
        "open_overtime_sessions": open_ot, "monthly_salary": money(prorated_total),
        "derived_daily_rate": money(prorated_total / Decimal(len(days))) if days else Decimal("0.00"),
        "overtime_hourly_rate": money(Decimal(latest.overtime_hourly_rate)),
        "late_deduction_amount": money(Decimal(latest.late_deduction_amount)), "compensation_periods": periods,
    }
