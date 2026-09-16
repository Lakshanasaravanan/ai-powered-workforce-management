"""InfoTech policy-QA endpoint, intentionally isolated from legacy tools."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.agents.infotech_intents import InfoTechIntent, InfoTechIntentRouter, format_read_result
from app.agents.models import PolicyExecutionContext, infotech_agent_context
from app.agents.apply_leave import parse_apply_leave
from app.agents.leave_decision import LeaveDecisionInput, parse_leave_decision
from app.services.infotech_pending_actions import InfoTechActionName, to_public
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


@router.post("/query", response_model=PolicyQueryResponse)
def query_policy(
    payload: PolicyQueryRequest,
    request: Request,
    identity: InfoTechIdentity,
    rag_service: RAGServiceDependency,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> PolicyQueryResponse:
    """Route only server-classified policy or read-only EMS intents."""
    context = PolicyExecutionContext(
        employee_id=identity.employee_id,
        employee_code=identity.employee_code,
        display_name=identity.display_name,
        role=identity.role,
        request_id=request_id_context.get(),
        conversation_id=payload.conversation_id or uuid4(),
    )
    decision = intent_router.route(payload.message)
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
        return PolicyQueryResponse(answer=answer, sources=[], conversation_id=context.conversation_id, request_id=context.request_id)
    if decision.intent is InfoTechIntent.LEAVE_DECISION_REQUEST:
        if identity.role != "MANAGER":
            return PolicyQueryResponse(
                answer="Leave decisions are available only to direct Managers.", sources=[],
                conversation_id=context.conversation_id, request_id=context.request_id,
                response_type="clarification",
            )
        parsed, clarification = parse_leave_decision(payload.message)
        if clarification:
            return PolicyQueryResponse(answer=clarification, sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        assert parsed is not None
        try:
            reference = request.app.state.infotech_decision_references.resolve(
                parsed.reference,
                manager_employee_id=identity.employee_id,
                conversation_id=context.conversation_id,
            )
        except DecisionReferenceExpired:
            return PolicyQueryResponse(answer="That leave reference has expired. Please refresh pending team leave requests.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        except (DecisionReferenceNotFound, DecisionReferenceBindingError, DecisionReferenceUnavailable, DecisionReferenceError):
            return PolicyQueryResponse(answer="That leave reference is unavailable. Please refresh pending team leave requests and use a displayed reference.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        try:
            leave = request.app.state.infotech_ems_client.get_leave(reference.leave_id, credentials.credentials)
            team_leaves = request.app.state.infotech_ems_client.get_team_leaves(credentials.credentials)
        except EMSReadClientError as exc:
            return PolicyQueryResponse(answer=_read_error_message(exc), sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        if (
            leave.id != reference.leave_id
            or leave.status != "PENDING"
            or not leave.approval_required
            or leave.leave_type == "MEDICAL"
            or not any(item.id == leave.id for item in team_leaves)
        ):
            return PolicyQueryResponse(answer="That leave request is no longer eligible for a Manager decision. Please refresh pending team leave requests.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        action_name = InfoTechActionName.APPROVE_LEAVE if parsed.operation == "approve" else InfoTechActionName.REJECT_LEAVE
        action_input = LeaveDecisionInput(leave_id=leave.id, decision_note=parsed.decision_note)
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
        public = to_public(action).model_dump(mode="json")
        return PolicyQueryResponse(answer="Please review and confirm this leave decision proposal.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="action_proposal", action=public)
    if decision.intent is InfoTechIntent.MUTATION_REQUEST:
        action_input, clarification = parse_apply_leave(payload.message)
        if clarification:
            return PolicyQueryResponse(answer=clarification, sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
        action = request.app.state.infotech_pending_actions.create(
            actor_employee_id=identity.employee_id, conversation_id=context.conversation_id,
            tool_name=InfoTechActionName.APPLY_LEAVE,
            validated_arguments=action_input.model_dump(mode="json"),
            safe_display={"title": f"Apply {action_input.leave_type.replace('_', ' ').title()} Leave", "date": action_input.start_date.isoformat(), "duration": action_input.duration.replace("_", " ").title(), "period": action_input.half_day_period.title() if action_input.half_day_period else None, "reason": action_input.reason},
        )
        public = to_public(action).model_dump(mode="json")
        return PolicyQueryResponse(answer="Please review and confirm this leave proposal.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="action_proposal", action=public)
    if decision.intent is InfoTechIntent.CONFIRMATION:
        return PolicyQueryResponse(answer="There is currently no executable pending action to confirm.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id)
    if decision.intent is InfoTechIntent.CANCELLATION:
        return PolicyQueryResponse(answer="There is currently no pending action to cancel.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id)
    if decision.intent is InfoTechIntent.CLARIFICATION:
        return PolicyQueryResponse(answer=decision.message or "Please clarify your request.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id, response_type="clarification")
    if decision.intent is InfoTechIntent.UNSUPPORTED:
        return PolicyQueryResponse(answer=decision.message or "This operational request is not supported by the InfoTech assistant.", sources=[], conversation_id=context.conversation_id, request_id=context.request_id)
    index = request.app.state.rag_index_status
    if not index.available:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Policy knowledge is unavailable; an operator must run the offline index build.")
    result = rag_service.answer(payload.message)
    answer, sources = result.answer, result.sources
    return PolicyQueryResponse(
        answer=answer,
        sources=sources,
        conversation_id=context.conversation_id,
        request_id=context.request_id,
    )
