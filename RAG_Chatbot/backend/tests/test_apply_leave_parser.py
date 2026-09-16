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
