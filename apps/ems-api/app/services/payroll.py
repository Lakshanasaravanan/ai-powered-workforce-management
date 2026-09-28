from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.attendance import AttendanceRecord, AttendanceStatus, OvertimeSession
from app.models.employee import CompensationConfiguration, Employee, Role
from app.models.payroll import PayrollSnapshot
from app.services.holidays import is_working_day


MONEY = Decimal("0.01")
REGULAR_REQUIREMENT_MINUTES = 480


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    if not 1 <= month <= 12 or not 2000 <= year <= 9999:
        raise HTTPException(422, "Invalid payroll month")
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def working_dates(db: Session, year: int, month: int) -> list[date]:
    _, end = month_bounds(year, month)
    return [date(year, month, day) for day in range(1, end.day + 1) if is_working_day(db, date(year, month, day))]


def qualifying_regular_minutes(record: AttendanceRecord) -> tuple[int | None, int | None]:
    if not record.regular_check_in_at or not record.regular_check_out_at:
        return None, None
    check_in, check_out = record.regular_check_in_at, record.regular_check_out_at
    start = check_in.replace(hour=9, minute=0, second=0, microsecond=0)
    end = check_in.replace(hour=17, minute=0, second=0, microsecond=0)
    credited_start, credited_end = max(check_in, start), min(check_out, end)
    qualifying = max(0, min(REGULAR_REQUIREMENT_MINUTES, int((credited_end - credited_start).total_seconds() // 60)))
    delay = max(0, int((check_in - start).total_seconds() // 60))
    return qualifying, delay


def _applicable_compensation(db: Session, employee_id, day: date) -> CompensationConfiguration | None:
    return db.query(CompensationConfiguration).filter(
        CompensationConfiguration.employee_id == employee_id,
        CompensationConfiguration.effective_from <= day,
        (CompensationConfiguration.effective_to.is_(None) | (CompensationConfiguration.effective_to >= day)),
    ).order_by(CompensationConfiguration.effective_from.desc()).first()


def payroll_preview(db: Session, employee: Employee, year: int, month: int) -> dict:
    if employee.role == Role.ADMIN:
        raise HTTPException(422, "Administrators are not payroll attendance subjects")
    start, end = month_bounds(year, month)
    days = working_dates(db, year, month)
    configs: dict[date, CompensationConfiguration] = {}
    for day in days:
        config = _applicable_compensation(db, employee.id, day)
        if not config:
            raise HTTPException(422, "No compensation configuration covers every company working day in this payroll month")
        configs[day] = config
    records = {row.attendance_date: row for row in db.query(AttendanceRecord).filter(
        AttendanceRecord.employee_id == employee.id, AttendanceRecord.attendance_date >= start, AttendanceRecord.attendance_date <= end,
    )}
    overtime_by_day: dict[date, int] = defaultdict(int)
    open_ot = 0
    for row in db.query(OvertimeSession).filter(OvertimeSession.employee_id == employee.id, OvertimeSession.attendance_date >= start, OvertimeSession.attendance_date <= end):
        if row.check_out_at is None:
            open_ot += 1
        else:
            overtime_by_day[row.attendance_date] += max(0, int((row.check_out_at - row.check_in_at).total_seconds() // 60))
    count = Decimal(len(days))
    counts: defaultdict[str, int] = defaultdict(int)
    minutes: defaultdict[str, int] = defaultdict(int)
    amounts: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    breakdown = []
    groups: dict[object, list[date]] = defaultdict(list)
    for day, config in configs.items():
        groups[config.id].append(day)
    for day in days:
        config, record = configs[day], records.get(day)
        daily_rate = Decimal(config.monthly_salary) / count if count else Decimal("0")
        classification = "MISSING_ATTENDANCE"
        qualifying = delay = deficit = recovery = unrecovered = paid_ot = raw_ot = 0
        late = absence = overtime_pay = Decimal("0")
        if not record:
            counts["missing"] += 1
        elif record.status == AttendanceStatus.LEAVE:
            classification = "PAID_LEAVE"; counts["paid_leave"] += 1
        elif record.status == AttendanceStatus.ABSENT:
            classification = "EXPLICIT_ABSENT"; counts["absent"] += 1; absence = daily_rate
        else:
            classification = "PRESENT"; counts["present"] += 1
            regular, delay_value = qualifying_regular_minutes(record)
            if regular is None:
                counts["incomplete_regular"] += 1
            else:
                qualifying, delay = regular, delay_value or 0
                raw_ot = overtime_by_day[day]
                deficit = max(0, REGULAR_REQUIREMENT_MINUTES - qualifying)
                recovery = min(deficit, raw_ot)
                unrecovered, paid_ot = deficit - recovery, raw_ot - recovery
                if unrecovered >= 60:
                    late = Decimal(config.late_deduction_amount)
                overtime_pay = Decimal(paid_ot) / Decimal(60) * Decimal(config.overtime_hourly_rate)
        for key, value in (("regular", qualifying), ("deficit", deficit), ("recovery", recovery), ("unrecovered", unrecovered), ("raw_ot", raw_ot), ("paid_ot", paid_ot)):
            minutes[key] += value
        if late: counts["late_days"] += 1
        if absence: counts["absence_days"] += 1
        amounts["late"] += late; amounts["absence"] += absence; amounts["overtime"] += overtime_pay
        breakdown.append({"date": day.isoformat(), "classification": classification, "regular_qualifying_minutes": qualifying, "arrival_delay_minutes": delay, "regular_deficit_minutes": deficit, "raw_overtime_minutes": raw_ot, "deficit_recovery_minutes": recovery, "unrecovered_deficit_minutes": unrecovered, "paid_overtime_minutes": paid_ot, "late_deduction_applied": bool(late), "late_deduction_amount": money(late), "absence_deduction": money(absence), "overtime_pay": money(overtime_pay)})
    periods, monthly_foundation = [], Decimal("0")
    for config_days in groups.values():
        config = configs[config_days[0]]; daily = Decimal(config.monthly_salary) / count if count else Decimal("0"); prorated = daily * Decimal(len(config_days)); monthly_foundation += prorated
        periods.append({"effective_from": max(start, config.effective_from).isoformat(), "effective_to": min(end, config.effective_to or end).isoformat(), "working_days": len(config_days), "monthly_salary": money(Decimal(config.monthly_salary)), "derived_daily_rate": money(daily), "prorated_salary_foundation": money(prorated), "overtime_hourly_rate": money(Decimal(config.overtime_hourly_rate)), "late_deduction_amount": money(Decimal(config.late_deduction_amount))})
    periods.sort(key=lambda item: item["effective_from"])
    latest = configs[days[-1]] if days else _applicable_compensation(db, employee.id, start)
    if not latest:
        raise HTTPException(422, "No compensation configuration covers this payroll month")
    regular_after_absence = monthly_foundation - amounts["absence"]
    return {"employee_id": str(employee.id), "employee_code": employee.employee_code, "employee_name": employee.full_name, "year": year, "month": month, "working_days": len(days), "present_days": counts["present"], "paid_leave_days": counts["paid_leave"], "explicit_absent_days": counts["absent"], "missing_attendance_days": counts["missing"], "regular_worked_minutes": minutes["regular"], "regular_records_without_completed_checkout": counts["incomplete_regular"], "raw_overtime_minutes": minutes["raw_ot"], "open_overtime_sessions": open_ot, "monthly_salary": money(monthly_foundation), "derived_daily_rate": money(monthly_foundation / count) if count else Decimal("0.00"), "overtime_hourly_rate": money(Decimal(latest.overtime_hourly_rate)), "late_deduction_amount": money(Decimal(latest.late_deduction_amount)), "compensation_periods": periods, "total_regular_qualifying_minutes": minutes["regular"], "total_regular_deficit_minutes": minutes["deficit"], "total_deficit_recovery_minutes": minutes["recovery"], "total_unrecovered_deficit_minutes": minutes["unrecovered"], "total_raw_overtime_minutes": minutes["raw_ot"], "total_paid_overtime_minutes": minutes["paid_ot"], "late_deduction_days": counts["late_days"], "total_late_deduction": money(amounts["late"]), "absence_deduction_days": counts["absence_days"], "total_absence_deduction": money(amounts["absence"]), "total_overtime_pay": money(amounts["overtime"]), "regular_salary_after_absence": money(regular_after_absence), "payable_salary_preview": money(regular_after_absence + amounts["overtime"] - amounts["late"]), "daily_breakdown": breakdown}


def _json_value(value):
    if isinstance(value, Decimal): return format(value, ".2f")
    if isinstance(value, (date, datetime)): return value.isoformat()
    if isinstance(value, list): return [_json_value(item) for item in value]
    if isinstance(value, dict): return {key: _json_value(item) for key, item in value.items()}
    return value


def snapshot_dict(snapshot: PayrollSnapshot) -> dict:
    return {"id": str(snapshot.id), "employee_id": str(snapshot.employee_id), "payroll_year": snapshot.payroll_year, "payroll_month": snapshot.payroll_month, "finalized_at": snapshot.finalized_at.isoformat(), "finalized_by_admin_id": str(snapshot.finalized_by_admin_id), "working_days": snapshot.working_days, "present_days": snapshot.present_days, "paid_leave_days": snapshot.paid_leave_days, "explicit_absent_days": snapshot.explicit_absent_days, "missing_attendance_days": snapshot.missing_attendance_days, "total_regular_qualifying_minutes": snapshot.total_regular_qualifying_minutes, "total_regular_deficit_minutes": snapshot.total_regular_deficit_minutes, "total_deficit_recovery_minutes": snapshot.total_deficit_recovery_minutes, "total_unrecovered_deficit_minutes": snapshot.total_unrecovered_deficit_minutes, "total_raw_overtime_minutes": snapshot.total_raw_overtime_minutes, "total_paid_overtime_minutes": snapshot.total_paid_overtime_minutes, "late_deduction_days": snapshot.late_deduction_days, "absence_deduction_days": snapshot.absence_deduction_days, "total_late_deduction": snapshot.total_late_deduction, "total_absence_deduction": snapshot.total_absence_deduction, "total_overtime_pay": snapshot.total_overtime_pay, "regular_salary_after_absence": snapshot.regular_salary_after_absence, "payable_salary": snapshot.payable_salary, "compensation_breakdown": snapshot.compensation_breakdown, "daily_breakdown": snapshot.daily_breakdown}
