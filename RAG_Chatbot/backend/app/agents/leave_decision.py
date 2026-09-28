"""Strict parsing and immutable inputs for future manager leave decisions.

This module deliberately has no EMS transport or execution behavior.  Step 5A
uses it only to construct a confirmation proposal from an opaque server-issued
reference.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LeaveDecisionInput(BaseModel):
    """Server-owned immutable decision payload stored in the pending action."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    leave_id: UUID
    decision_note: str | None = Field(default=None, max_length=1000)


DecisionOperation = Literal["approve", "reject"]


@dataclass(frozen=True, slots=True)
class ParsedLeaveDecision:
    operation: DecisionOperation
    reference: str
    decision_note: str | None


_DECISION = re.compile(
    r"^\s*(approve|reject)\s+(?:leave\s+)?(LR-[A-F0-9]{20})(?:\s+because\s+(.+?))?\s*[.!]?\s*$",
    re.IGNORECASE,
)


def parse_leave_decision(message: str) -> tuple[ParsedLeaveDecision | None, str | None]:
    """Accept an exact opaque reference only; never guess a leave target."""

    match = _DECISION.fullmatch(message)
    if match is None:
        return None, "Please refresh pending team leave requests and use the displayed leave reference (for example, Approve LR-…)."
    note = match.group(3)
    normalized_note = " ".join(note.split()) if note else None
    if normalized_note is not None and len(normalized_note) > 1000:
        return None, "The decision note is too long."
    return ParsedLeaveDecision(
        operation=match.group(1).lower(),
        reference=match.group(2).upper(),
        decision_note=normalized_note,
    ), None
