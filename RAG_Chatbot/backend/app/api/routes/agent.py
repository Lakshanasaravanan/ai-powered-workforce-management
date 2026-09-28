"""InfoTech policy-QA endpoint, intentionally isolated from legacy tools."""

from __future__ import annotations

from datetime import date, timedelta
import calendar
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.agents.infotech_intents import InfoTechIntent, InfoTechIntentRouter, format_read_result
from app.agents.semantic_routing import READ_TOOL_BY_OPERATION, SemanticCategory
from app.agents.models import PolicyExecutionContext, infotech_agent_context
from app.agents.apply_leave import ApplyLeaveInput, extract_leave_slots, parse_apply_leave
from app.agents.leave_decision import LeaveDecisionInput, parse_leave_decision
from app.services.infotech_pending_actions import InfoTechActionName, PendingActionError, PendingActionStoreUnavailable, to_public
from uuid import UUID
from app.services.infotech_conversations import ConversationRole, ConversationStoreError
from app.services.infotech_decision_references import (
    DecisionReferenceBindingError,
    DecisionReferenceError,
    DecisionReferenceExpired,
    DecisionReferenceNotFound,
    DecisionReferenceUnavailable,
)
from app.api.dependencies import InfoTechIdentity, RAGServiceDependency, bearer_scheme
from app.core.logging import request_id_context
from app.schemas.policy import PolicyQueryRequest, PolicyQueryResponse
from app.services.infotech_ems import (
    EMSConflict,
    EMSForbidden,
    EMSRateLimited,
    EMSReadClientError,
    EMSUnauthorized,
    EMSUnavailable,
)
from app.tools.infotech_ems import InfoTechUnauthorizedTool


router = APIRouter(prefix="/api/v1/agent", tags=["infotech-policy-agent"])
intent_router = InfoTechIntentRouter()


def _read_error_message(error: EMSReadClientError) -> str:
    if isinstance(error, EMSUnauthorized):
        return "Your EMS session is no longer valid. Please sign in again."
    if isinstance(error, EMSForbidden):
        return "You are not authorized to view that information."
    if isinstance(error, EMSConflict):
        return "The requested information changed and could not be retrieved safely."
    if isinstance(error, EMSRateLimited):
        return "EMS is temporarily rate limited. Please try again shortly."
    if isinstance(error, EMSUnavailable):
        return "InfoTech EMS is temporarily unavailable. Please try again later."
    return "InfoTech EMS could not safely complete that request."


def _semantic_route(request: Request, message: str):
    """Resolve only a closed, schema-validated semantic route for unknown text."""
    classifier = getattr(request.app.state, "semantic_intent_router", None)
    return classifier.classify(message) if classifier is not None else None


def _proposal_storage_error(exc: PendingActionError) -> HTTPException:
    if isinstance(exc, PendingActionStoreUnavailable):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Action preparation is temporarily unavailable")
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Action preparation could not be completed safely")


def _conversation_error(_: ConversationStoreError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Conversation storage is temporarily unavailable")


def _respond(request: Request, identity: InfoTechIdentity, conversation_id, response: PolicyQueryResponse) -> PolicyQueryResponse:
    """Persist only the visible response; credentials and tool internals stay request-local."""
    try:
        request.app.state.infotech_conversations.append(
            identity.employee_id, conversation_id, role=ConversationRole.ASSISTANT,
            content=response.answer,
            sources=[source.model_dump(mode="json") for source in response.sources],
            action=response.action,
        )
    except ConversationStoreError as exc:
        raise _conversation_error(exc) from exc
    return response


def _leave_proposal(request: Request, identity: InfoTechIdentity, context: PolicyExecutionContext, action_input: ApplyLeaveInput) -> PolicyQueryResponse:
    try:
        action = request.app.state.infotech_pending_actions.create(
            actor_employee_id=identity.employee_id, conversation_id=context.conversation_id,
            tool_name=InfoTechActionName.APPLY_LEAVE,
            validated_arguments=action_input.model_dump(mode="json"),
            safe_display={"title": f"Apply {action_input.leave_type.replace('_', ' ').title()} Leave", "date": action_input.start_date.isoformat(), "end_date": action_input.end_date.isoformat(), "duration": action_input.duration.replace("_", " ").title(), "period": action_input.half_day_period.title() if action_input.half_day_period else None, "reason": action_input.reason},
        )
    except PendingActionError as exc:
        raise _proposal_storage_error(exc) from exc
    # Keep only the opaque action identifier in conversation state. The
    # immutable arguments and idempotency key remain in the action store.
    request.app.state.infotech_conversations.set_pending(
        identity.employee_id, context.conversation_id, {
            "action_id": str(action.action_id), "leave_type": action_input.leave_type,
            "start_date": action_input.start_date.isoformat(), "end_date": action_input.end_date.isoformat(),
            "reason": action_input.reason,
        }
    )
    return PolicyQueryResponse(
        answer="Please review and confirm this leave proposal.", sources=[], conversation_id=context.conversation_id,
        request_id=context.request_id, response_type="action_proposal", action=to_public(action).model_dump(mode="json"),
    )


def _has_working_day(request: Request, start: date, end: date, bearer: str) -> tuple[bool, str | None]:
    client = request.app.state.infotech_ems_client
    # Older injected test doubles predate the optional UX preflight. EMS still
    # remains authoritative at confirmation/execution in those environments.
    if not hasattr(client, "get_working_day"):
        return True, None
    cursor = start
    reason: str | None = None
    while cursor <= end:
        item = client.get_working_day(cursor, bearer)
        if item.is_working_day:
            return True, None
        reason = item.reason
        cursor += timedelta(days=1)
    return False, reason


def _period_from_message(message: str, *, previous: dict | None = None) -> tuple[date, date]:
    """Bounded month/day parser for fixed EMS read endpoints."""
    today = date.today()
    text = message.lower()
    if "yesterday" in text:
        day = today - timedelta(days=1); return day, day
    if "today" in text:
        return today, today
    if "last month" in text:
        first = today.replace(day=1) - timedelta(days=1); return first.replace(day=1), first
    match = re.search(r"\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+(20\d{2})\b", text)
    if match:
        month = list(calendar.month_name).index(match.group(1).title()); year = int(match.group(2))
        return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
    if previous and previous.get("start") and previous.get("end") and "what about" in text:
        start = date.fromisoformat(previous["start"]); prior_end = start - timedelta(days=1)
        return prior_end.replace(day=1), prior_end
    return today.replace(day=1), date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])


def _employee_code(message: str) -> str | None:
    found = re.search(r"\b[A-Z]{2,}\d{2,}\b", message.upper())
    return found.group(0) if found else None


def _attendance_answer(feed: dict) -> str:
    records = feed.get("records", [])
    if not records:
        return "No attendance records were returned for that period."
    present = sum(item.get("status") == "PRESENT" for item in records)
    late = sum((item.get("late_minutes") or 0) > 0 for item in records)
    overtime = sum(item.get("worked_minutes") or 0 for item in records)
    return f"Attendance records: {present} present, {late} late arrival(s), across {len(records)} recorded day(s). Regular recorded minutes: {overtime}."


def _payroll_answer(payload: dict | list[dict], *, history: bool = False) -> str:
    if history:
        return f"Finalized payroll history contains {len(payload)} record(s)."
    assert isinstance(payload, dict)
    amount = payload.get("payable_salary") or payload.get("payable_salary_preview")
    return f"Authorized payroll result for {payload.get('payroll_year', '')}-{payload.get('payroll_month', '')}: payable salary {amount}."


@router.post("/query", response_model=PolicyQueryResponse)
def query_policy(
    payload: PolicyQueryRequest,
    request: Request,
    identity: InfoTechIdentity,
    rag_service: RAGServiceDependency,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> PolicyQueryResponse:
    """Route only server-classified policy or read-only EMS intents."""
    try:
        conversation = request.app.state.infotech_conversations.get_or_create(identity.employee_id, payload.conversation_id)
        request.app.state.infotech_conversations.append(
            identity.employee_id, conversation.id, role=ConversationRole.USER, content=payload.message
        )
    except ConversationStoreError as exc:
        raise _conversation_error(exc) from exc
    context = PolicyExecutionContext(
        employee_id=identity.employee_id,
        employee_code=identity.employee_code,
        display_name=identity.display_name,
        role=identity.role,
        request_id=request_id_context.get(),
        conversation_id=conversation.id,
    )
    decision = intent_router.route(payload.message)
    # Structured collecting state takes priority over generic routing, but only
    # in the exact conversation that owns it.
    pending = request.app.state.infotech_conversations.get(identity.employee_id, context.conversation_id).pending
    if pending is not None:
        action_id = pending.slots.get("action_id")
        if action_id and decision.intent is InfoTechIntent.CONFIRMATION:
            try:
                claimed = request.app.state.infotech_pending_actions.claim(UUID(action_id), identity.employee_id, context.conversation_id)
                leave = ApplyLeaveInput.model_validate(claimed.validated_arguments)
                request.app.state.infotech_ems_client.apply_leave(leave, credentials.credentials, claimed.idempotency_key, context.request_id)
                request.app.state.infotech_pending_actions.finish_succeeded(claimed.action_id, identity.employee_id, context.conversation_id)
                request.app.state.infotech_conversations.clear_pending(identity.employee_id, context.conversation_id)
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="Leave request was submitted to EMS.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
            except (PendingActionError, EMSReadClientError, ValueError) as exc:
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_read_error_message(exc) if isinstance(exc, EMSReadClientError) else "That action is no longer available for confirmation.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        if decision.intent is InfoTechIntent.CANCELLATION:
            if action_id:
                try: request.app.state.infotech_pending_actions.cancel(UUID(action_id), identity.employee_id, context.conversation_id)
                except (PendingActionError, ValueError): pass
            request.app.state.infotech_conversations.clear_pending(identity.employee_id, context.conversation_id)
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                answer="Your pending leave request was cancelled.", sources=[], conversation_id=context.conversation_id,
                request_id=context.request_id,
            ))
        if decision.intent is not InfoTechIntent.CONFIRMATION:
            slots = {**pending.slots, **extract_leave_slots(payload.message)}
            missing = [name for name in ("start_date", "end_date", "leave_type", "reason") if not slots.get(name)]
            if missing:
                request.app.state.infotech_conversations.set_pending(identity.employee_id, context.conversation_id, slots)
                labels = {"leave_type": "leave type (Casual, Medical, Emergency, or Day Off)", "reason": "reason", "start_date": "date", "end_date": "end date"}
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                    answer=f"Please provide the remaining {labels[missing[0]]}.", sources=[],
                    conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification",
                ))
            action_input = ApplyLeaveInput(
                leave_type=slots["leave_type"], start_date=date.fromisoformat(slots["start_date"]),
                end_date=date.fromisoformat(slots["end_date"]), duration="FULL_DAY", reason=slots["reason"],
            )
            try:
                any_working_day, reason = _has_working_day(request, action_input.start_date, action_input.end_date, credentials.credentials)
            except EMSReadClientError as exc:
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                    answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id,
                    request_id=context.request_id, response_type="clarification",
                ))
            if not any_working_day:
                request.app.state.infotech_conversations.clear_pending(identity.employee_id, context.conversation_id)
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                    answer=f"That date is a company non-working day{f' ({reason})' if reason else ''}; no leave request is needed.",
                    sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification",
                ))
            if action_id:
                try:
                    request.app.state.infotech_pending_actions.cancel(UUID(action_id), identity.employee_id, context.conversation_id)
                except (PendingActionError, ValueError):
                    pass
            request.app.state.infotech_conversations.clear_pending(identity.employee_id, context.conversation_id)
            return _respond(request, identity, context.conversation_id, _leave_proposal(request, identity, context, action_input))
    normalized = payload.message.lower()
    previous_user = next((message.content for message in reversed(conversation.messages) if message.role is ConversationRole.USER), "")
    is_follow_up = "what about" in normalized and bool(previous_user)
    if "attendance" in normalized or "late" in normalized or "overtime" in normalized or (is_follow_up and "attendance" in previous_user.lower()):
        if identity.role == "ADMIN" and _employee_code(payload.message) is None:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="Administrators do not have attendance records. Please specify an employee code.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        try:
            code = _employee_code(payload.message)
            target = None
            if code:
                matches = request.app.state.infotech_ems_client.search_employees(code, credentials.credentials)
                target = next((item for item in matches if item.employee_code == code), None)
                if target is None:
                    return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="No matching active employee was found.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
            start, end = _period_from_message(payload.message)
            feed = request.app.state.infotech_ems_client.get_attendance(target.id if target else None, start, end, credentials.credentials)
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_attendance_answer(feed), sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
        except EMSReadClientError as exc:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
    if "payroll" in normalized or "salary" in normalized or (is_follow_up and ("payroll" in previous_user.lower() or "salary" in previous_user.lower())):
        if identity.role != "ADMIN":
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="Payroll information is available only to Administrators.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        code = _employee_code(payload.message) or _employee_code(previous_user)
        if code is None:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="Please specify an employee code for the payroll request.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        try:
            matches = request.app.state.infotech_ems_client.search_employees(code, credentials.credentials)
            target = next((item for item in matches if item.employee_code == code), None)
            if target is None:
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="No matching active employee was found.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
            if "history" in normalized:
                result = request.app.state.infotech_ems_client.get_finalized_payroll_history(target.id, credentials.credentials)
                answer = _payroll_answer(result, history=True)
            else:
                start, _ = _period_from_message(payload.message, previous={"start": date.today().replace(day=1).isoformat(), "end": date.today().isoformat()} if is_follow_up else None)
                if "finalized" in normalized or (is_follow_up and "finalized" in previous_user.lower()):
                    result = request.app.state.infotech_ems_client.get_finalized_payroll(target.id, start.year, start.month, credentials.credentials)
                else:
                    result = request.app.state.infotech_ems_client.get_payroll_preview(target.id, start.year, start.month, credentials.credentials)
                answer = _payroll_answer(result)
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=answer, sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
        except EMSReadClientError as exc:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
    if decision.intent is InfoTechIntent.GENERAL_CONVERSATION:
        semantic = _semantic_route(request, payload.message)
        if semantic is None:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                answer="I couldn’t safely classify that request. I can help with general questions, company policies, your available workforce information, or a supported leave request.",
                sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification",
            ))
        if semantic.category is SemanticCategory.GENERAL:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                answer=semantic.general_response.strip(), sources=[], conversation_id=context.conversation_id,
                request_id=context.request_id,
            ))
        if semantic.category is SemanticCategory.POLICY:
            decision = type(decision)(InfoTechIntent.POLICY_QA)
        elif semantic.category is SemanticCategory.EMS_READ:
            decision = type(decision)(InfoTechIntent.READ_ACTION, READ_TOOL_BY_OPERATION[semantic.read_operation])
        elif semantic.category is SemanticCategory.EMS_ACTION_LEAVE:
            decision = type(decision)(InfoTechIntent.MUTATION_REQUEST)
        else:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                answer="I don’t have an authorized source for that company-specific request. I can help with documented policies, your available workforce information, or a supported leave request.",
                sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification",
            ))
    if decision.intent is InfoTechIntent.READ_ACTION:
        tool_context = infotech_agent_context(identity, context.request_id, context.conversation_id)
        try:
            result = request.app.state.infotech_read_registry.execute(
                decision.tool_name, tool_context, credentials.credentials, {}
            )
            references: dict[str, str] | None = None
            if decision.tool_name == "get_team_leaves" and identity.role == "MANAGER":
                references = {}
                for leave in result:
                    if leave.status == "PENDING" and leave.approval_required and leave.leave_type != "MEDICAL":
                        issued = request.app.state.infotech_decision_references.issue(
                            manager_employee_id=identity.employee_id,
                            conversation_id=context.conversation_id,
                            leave_id=leave.id,
                        )
                        references[str(leave.id)] = issued.reference
            answer = format_read_result(decision.tool_name, result, decision_references=references)
        except InfoTechUnauthorizedTool:
            answer = "This read capability is available only to Managers."
        except DecisionReferenceUnavailable:
            answer = "Pending team leave requests are available, but decision references are temporarily unavailable. Please try again later."
        except EMSReadClientError as exc:
            answer = _read_error_message(exc)
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=answer, sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
    if decision.intent is InfoTechIntent.LEAVE_DECISION_REQUEST:
        if identity.role != "MANAGER":
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                answer="Leave decisions are available only to direct Managers.", sources=[],
                conversation_id=context.conversation_id, request_id=context.request_id,
                response_type="clarification",
            ))
        parsed, clarification = parse_leave_decision(payload.message)
        if clarification:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=clarification, sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        assert parsed is not None
        try:
            reference = request.app.state.infotech_decision_references.resolve(
                parsed.reference,
                manager_employee_id=identity.employee_id,
                conversation_id=context.conversation_id,
            )
        except DecisionReferenceExpired:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="That leave reference has expired. Please refresh pending team leave requests.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        except (DecisionReferenceNotFound, DecisionReferenceBindingError, DecisionReferenceUnavailable, DecisionReferenceError):
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="That leave reference is unavailable. Please refresh pending team leave requests and use a displayed reference.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        try:
            leave = request.app.state.infotech_ems_client.get_leave(reference.leave_id, credentials.credentials)
            team_leaves = request.app.state.infotech_ems_client.get_team_leaves(credentials.credentials)
        except EMSReadClientError as exc:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        if (
            leave.id != reference.leave_id
            or leave.status != "PENDING"
            or not leave.approval_required
            or leave.leave_type == "MEDICAL"
            or not any(item.id == leave.id for item in team_leaves)
        ):
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="That leave request is no longer eligible for a Manager decision. Please refresh pending team leave requests.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        action_name = InfoTechActionName.APPROVE_LEAVE if parsed.operation == "approve" else InfoTechActionName.REJECT_LEAVE
        action_input = LeaveDecisionInput(leave_id=leave.id, decision_note=parsed.decision_note)
        try:
            action = request.app.state.infotech_pending_actions.create(
                actor_employee_id=identity.employee_id,
                conversation_id=context.conversation_id,
                tool_name=action_name,
                validated_arguments=action_input.model_dump(mode="json"),
                target_entity_id=leave.id,
                safe_display={
                    "title": f"{'Approve' if parsed.operation == 'approve' else 'Reject'} leave request",
                    "employee": f"{leave.employee.full_name} ({leave.employee.employee_code})",
                    "leave_type": leave.leave_type.title(),
                    "dates": f"{leave.start_date.isoformat()} to {leave.end_date.isoformat()}",
                    "status": "Pending",
                    "decision": parsed.operation.title(),
                    "decision_note": parsed.decision_note,
                },
            )
        except PendingActionError as exc:
            raise _proposal_storage_error(exc) from exc
        public = to_public(action).model_dump(mode="json")
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="Please review and confirm this leave decision proposal.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="action_proposal", action=public))
    if decision.intent is InfoTechIntent.MUTATION_REQUEST:
        action_input, clarification = parse_apply_leave(payload.message)
        if clarification:
            slots = extract_leave_slots(payload.message)
            if "start_date" in slots and "leave_type" not in slots:
                request.app.state.infotech_conversations.set_pending(identity.employee_id, context.conversation_id, slots)
                return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
                    answer="Please provide the leave type (Casual, Medical, Emergency, or Day Off).", sources=[],
                    conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification",
                ))
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=clarification, sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        try:
            any_working_day, reason = _has_working_day(request, action_input.start_date, action_input.end_date, credentials.credentials)
        except EMSReadClientError as exc:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        if not any_working_day:
            return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=f"That date is a company non-working day{f' ({reason})' if reason else ''}; no leave request is needed.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
        return _respond(request, identity, context.conversation_id, _leave_proposal(request, identity, context, action_input))
    if decision.intent is InfoTechIntent.CONFIRMATION:
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="There is currently no executable pending action to confirm.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
    if decision.intent is InfoTechIntent.CANCELLATION:
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer="There is currently no pending action to cancel.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
    if decision.intent is InfoTechIntent.CLARIFICATION:
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=decision.message or "Please clarify your request.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification"))
    if decision.intent is InfoTechIntent.UNSUPPORTED:
        return _respond(request, identity, context.conversation_id, PolicyQueryResponse(answer=decision.message or "This operational request is not supported by the InfoTech assistant.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id))
    index = request.app.state.rag_index_status
    if not index.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Policy knowledge is unavailable; an operator must run the offline index build.")
    result = rag_service.answer(payload.message)
    answer, sources = result.answer, result.sources
    return _respond(request, identity, context.conversation_id, PolicyQueryResponse(
        answer=answer,
        sources=sources,
        conversation_id=context.conversation_id,
        request_id=context.request_id,
    ))
