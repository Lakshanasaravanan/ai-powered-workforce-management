from datetime import date

import pytest

from app.agents.apply_leave import parse_apply_leave


@pytest.mark.parametrize("message,leave_type,period", [
    ("Apply casual leave tomorrow because of a family visit.", "CASUAL", None),
    ("Apply medical leave tomorrow because I have fever.", "MEDICAL", None),
    ("Apply emergency leave tomorrow because of a family emergency.", "EMERGENCY", None),
    ("Take a day off tomorrow morning because I have an appointment.", "DAY_OFF", "MORNING"),
    ("Take a day off tomorrow afternoon because I have an appointment.", "DAY_OFF", "AFTERNOON"),
])
def test_complete_bounded_apply_leave_forms_are_immutable_typed_inputs(message, leave_type, period):
    value, clarification = parse_apply_leave(message, today=date(2027, 1, 1))
    assert clarification is None
    assert value.leave_type == leave_type and value.start_date.isoformat() == "2027-01-02"
    assert value.half_day_period == period


@pytest.mark.parametrize("message", [
    "Apply leave tomorrow.",
    "Apply casual leave tomorrow.",
    "Take a day off tomorrow because I have an appointment.",
    "Apply casual leave next week because I need time.",
])
def test_incomplete_or_ambiguous_leave_requests_clarify_without_a_payload(message):
    value, clarification = parse_apply_leave(message, today=date(2027, 1, 1))
    assert value is None and clarification


@pytest.mark.parametrize("message", [
    "Apply for casual leave on September 25, 2026 because of a family visit.",
    "Apply for casual leave on Sep 25, 2026 because of a family visit.",
    "Apply for casual leave on 25 September 2026 because of a family visit.",
    "Apply for casual leave on 25 Sep 2026 because of a family visit.",
])
def test_month_name_dates_preserve_the_requested_calendar_day(message):
    value, clarification = parse_apply_leave(message, today=date(2027, 1, 1))
    assert clarification is None
    assert value is not None and value.start_date == value.end_date == date(2026, 9, 25)


@pytest.mark.parametrize("message", [
    "Apply for casual leave on September 25, 2026.",
    "Apply for casual leave on Sep 25, 2026.",
    "Apply for casual leave on 25 September 2026.",
    "Apply for casual leave on 25 Sep 2026.",
])
def test_month_name_dates_are_recognized_even_when_the_reason_is_still_needed(message):
    value, clarification = parse_apply_leave(message, today=date(2027, 1, 1))
    assert value is None and clarification is not None
    assert "reason" in clarification.lower() and "ambiguous" not in clarification.lower()


def test_numeric_and_impossible_dates_are_safely_clarified():
    numeric, numeric_clarification = parse_apply_leave("Apply casual leave on 03/04/2026 because of a family visit.")
    impossible, impossible_clarification = parse_apply_leave("Apply casual leave on February 30, 2026 because of a family visit.")
    assert numeric is None and "ambiguous" in numeric_clarification.lower()
    assert impossible is None and "not valid" in impossible_clarification.lower()
