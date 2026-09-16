"""Deterministic, bounded intent routing for InfoTech EMS read operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.services.infotech_ems import EMSLeave, EMSNotification, EMSProfile, EMSUnreadCount


class InfoTechIntent(StrEnum):
    POLICY_QA = "policy_qa"
    READ_ACTION = "read_action"
    MUTATION_REQUEST = "mutation_request"
    LEAVE_DECISION_REQUEST = "leave_decision_request"
    CONFIRMATION = "confirmation"
    CANCELLATION = "cancellation"
    CLARIFICATION = "clarification"
    UNSUPPORTED = "unsupported"


READ_TOOL_NAMES = frozenset({"get_my_profile", "get_my_leaves", "get_my_notifications", "get_unread_notification_count", "get_direct_reports", "get_team_leaves"})


@dataclass(frozen=True, slots=True)
class InfoTechIntentDecision:
    intent: InfoTechIntent
    tool_name: str | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.intent is InfoTechIntent.READ_ACTION and self.tool_name not in READ_TOOL_NAMES:
            raise ValueError("Read actions require an allowlisted tool name")
        if self.intent is not InfoTechIntent.READ_ACTION and self.tool_name is not None:
            raise ValueError("Only read actions may select a tool")


class InfoTechIntentRouter:
    """Phrase-bounded router. It never invokes a model or chooses dynamic tools."""

    _confirmation = re.compile(r"^(?:yes(?:,?\s*confirm)?|confirm|go ahead)$", re.IGNORECASE)
    _cancellation = re.compile(r"^(?:cancel(?: that)?|never mind)$", re.IGNORECASE)
    _balance = re.compile(r"\b(?:leave balance|leaves? (?:do i|can i) have left|leaves? remaining|remaining (?:casual|medical|sick)? ?leaves?)\b", re.IGNORECASE)
    _mutation = re.compile(r"\b(?:apply|request|take|approve|reject|mark)\b.*\b(?:leave|day off|notification|inbox)\b", re.IGNORECASE)
    _leave_decision = re.compile(r"^\s*(?:approve|reject)\b", re.IGNORECASE)
    _unsupported = re.compile(r"\b(?:attendance|payroll|salary|delete[_\s]+employee|create\s+(?:an?\s+)?employee|edit\s+(?:an?\s+)?employee|deactivate\s+(?:an?\s+)?employee|another employee|someone else(?:'s)? (?:profile|leaves?)|employee_id|manager_id|call a tool|tool named|ignore your rules|call\s+get_[a-z_]+)\b", re.IGNORECASE)
    _policy = re.compile(r"\b(?:what is|explain|does|policy|code of conduct|security policy|it security|casual leave|medical leave|day off)\b", re.IGNORECASE)

    def route(self, message: str) -> InfoTechIntentDecision:
        normalized = " ".join(message.strip().lower().split())
        if self._confirmation.fullmatch(normalized):
            return InfoTechIntentDecision(InfoTechIntent.CONFIRMATION)
        if self._cancellation.fullmatch(normalized):
            return InfoTechIntentDecision(InfoTechIntent.CANCELLATION)
        if self._leave_decision.match(normalized):
            return InfoTechIntentDecision(InfoTechIntent.LEAVE_DECISION_REQUEST)
        if self._balance.search(normalized):
            return InfoTechIntentDecision(InfoTechIntent.UNSUPPORTED, message="Leave balance is unavailable because InfoTech EMS does not yet have an authoritative entitlement or accrual engine.")
        if self._mutation.search(normalized):
            return InfoTechIntentDecision(InfoTechIntent.MUTATION_REQUEST)
        if self._unsupported.search(normalized):
            return InfoTechIntentDecision(InfoTechIntent.UNSUPPORTED, message="This operational request is not supported by the InfoTech assistant.")
        if self._policy.search(normalized) and not normalized.startswith(("show my", "what leaves have", "what notifications", "how many unread", "who reports", "what is the status of my", "what is my employee code", "what is my profile", "what department am i", "what is my designation")):
            return InfoTechIntentDecision(InfoTechIntent.POLICY_QA)
        if any(phrase in normalized for phrase in ("how many unread notifications", "do i have unread notifications", "unread notification count")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_unread_notification_count")
        if any(phrase in normalized for phrase in ("show my notifications", "show my inbox", "what notifications do i have", "show my recent notifications")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_my_notifications")
        if any(phrase in normalized for phrase in ("who reports to me", "show my direct reports", "show my team members")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_direct_reports")
        if any(phrase in normalized for phrase in ("show team leaves", "show my team leaves", "show my team's leave requests", "which of my direct reports have requested leave", "show pending team leave requests", "show my pending team leave requests")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_team_leaves")
        if any(phrase in normalized for phrase in ("show my profile", "what is my profile", "show my employee details", "what is my employee code", "what department am i in", "what is my designation")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_my_profile")
        if any(phrase in normalized for phrase in ("show my leaves", "show my leave requests", "what leaves have i applied for", "show my leave history", "what is the status of my leave requests", "show my casual leave requests", "show my medical leave requests")):
            return InfoTechIntentDecision(InfoTechIntent.READ_ACTION, "get_my_leaves")
        if normalized in {"show leave", "show leaves", "leave status", "my leave"}:
            return InfoTechIntentDecision(InfoTechIntent.CLARIFICATION, message="Do you want policy guidance, your leave requests, or—if you are a Manager—team leave requests?")
        return InfoTechIntentDecision(InfoTechIntent.POLICY_QA)


def format_read_result(tool_name: str, result, *, decision_references: dict[str, str] | None = None) -> str:
    """Format typed EMS records deterministically; operational data never gets citations."""
    if tool_name == "get_my_profile":
        assert isinstance(result, EMSProfile)
        manager = "No manager is assigned" if result.manager_id is None else "A manager is assigned"
        return f"{result.full_name} ({result.employee_code}) — {result.designation} in {result.department}. {manager}."
    if tool_name == "get_unread_notification_count":
        assert isinstance(result, EMSUnreadCount)
        return f"You have {result.unread_count} unread notification{'s' if result.unread_count != 1 else ''}."
    if tool_name == "get_my_leaves":
        if not result: return "You don't have any leave requests yet."
        assert all(isinstance(item, EMSLeave) for item in result)
        return "Your leave requests: " + "; ".join(f"{item.leave_type} {item.start_date} to {item.end_date} — {item.status}" for item in result[:10])
    if tool_name == "get_team_leaves":
        if not result: return "There are no team leave requests to show."
        assert all(isinstance(item, EMSLeave) for item in result)
        entries = []
        for item in result[:10]:
            period = f" ({item.half_day_period.title()})" if item.half_day_period else ""
            entry = f"{item.employee.full_name} ({item.employee.employee_code}): {item.leave_type} {item.start_date} to {item.end_date}{period} — {item.status}"
            reference = (decision_references or {}).get(str(item.id))
            if reference:
                entry += f" — Reference: {reference}"
            entries.append(entry)
        return "Team leave requests: " + "; ".join(entries)
    if tool_name == "get_my_notifications":
        if not result: return "You don't have any notifications."
        assert all(isinstance(item, EMSNotification) for item in result)
        return "Your notifications: " + "; ".join(f"{item.title} ({'read' if item.is_read else 'unread'})" for item in result[:10])
    if tool_name == "get_direct_reports":
        if not result: return "You don't currently have any direct reports."
        assert all(isinstance(item, EMSProfile) for item in result)
        return "Your direct reports: " + "; ".join(f"{item.full_name} ({item.employee_code})" for item in result[:10])
    raise ValueError("Unknown InfoTech read tool")
