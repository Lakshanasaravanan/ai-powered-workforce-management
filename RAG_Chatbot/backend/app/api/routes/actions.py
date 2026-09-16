"""Authenticated InfoTech action lifecycle endpoints; Step 3 never mutates EMS."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from uuid import UUID
from app.api.dependencies import InfoTechIdentity, bearer_scheme
from fastapi.security import HTTPAuthorizationCredentials
from app.agents.apply_leave import ApplyLeaveInput
from app.agents.leave_decision import LeaveDecisionInput
from app.services.infotech_ems import EMSReadClientError, EMSUncertainOutcome
from app.services.infotech_pending_actions import InfoTechActionName
from app.core.logging import request_id_context
from app.schemas.actions import ActionConversationRequest, ActionStateResponse
from app.services.infotech_pending_actions import (
    PendingActionError, PendingActionExpired, PendingActionStateError,
    PendingActionStoreUnavailable, PendingActionUnavailable,
)

router = APIRouter(prefix="/api/v1/agent/actions", tags=["infotech-agent-actions"])

def _error(exc: PendingActionError) -> HTTPException:
    if isinstance(exc, PendingActionStoreUnavailable):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Pending actions are temporarily unavailable")
    if isinstance(exc, PendingActionExpired):
        return HTTPException(status.HTTP_409_CONFLICT, "Pending action has expired")
    if isinstance(exc, PendingActionStateError):
        return HTTPException(status.HTTP_409_CONFLICT, "Pending action is unavailable")
    return HTTPException(status.HTTP_404_NOT_FOUND, "Pending action is unavailable")

@router.post("/{action_id}/confirm", response_model=ActionStateResponse)
def confirm(
    action_id: UUID,
    body: ActionConversationRequest,
    request: Request,
    identity: InfoTechIdentity,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> ActionStateResponse:
    """Claim then execute exactly the immutable apply-leave payload, without RAG."""
    try:
        claimed = request.app.state.infotech_pending_actions.claim(action_id, identity.employee_id, body.conversation_id)
        if claimed.tool_name is InfoTechActionName.APPLY_LEAVE:
            leave = ApplyLeaveInput.model_validate(claimed.validated_arguments)
            request.app.state.infotech_ems_client.apply_leave(leave, credentials.credentials, claimed.idempotency_key, request_id_context.get())
            message = "Leave request was submitted to EMS."
        elif claimed.tool_name is InfoTechActionName.APPROVE_LEAVE:
            decision = LeaveDecisionInput.model_validate(claimed.validated_arguments)
            request.app.state.infotech_ems_client.approve_leave(decision, credentials.credentials, claimed.idempotency_key, request_id_context.get())
            message = "Leave request was approved in EMS."
        elif claimed.tool_name is InfoTechActionName.REJECT_LEAVE:
            decision = LeaveDecisionInput.model_validate(claimed.validated_arguments)
            request.app.state.infotech_ems_client.reject_leave(decision, credentials.credentials, claimed.idempotency_key, request_id_context.get())
            message = "Leave request was rejected in EMS."
        else:
            raise PendingActionStateError("Pending action is unavailable")
        action = request.app.state.infotech_pending_actions.finish_succeeded(action_id, identity.employee_id, body.conversation_id)
    except EMSUncertainOutcome:
        # Do not mark failure: stale lease recovery retries the same EMS key.
        raise HTTPException(status.HTTP_202_ACCEPTED, "Action outcome is pending safe recovery")
    except EMSReadClientError:
        request.app.state.infotech_pending_actions.finish_failed(action_id, identity.employee_id, body.conversation_id)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "EMS rejected the leave request")
    except PendingActionError as exc:
        raise _error(exc) from exc
    return ActionStateResponse(action_id=action.action_id, state=action.state, message=message, conversation_id=body.conversation_id, request_id=request_id_context.get())

@router.post("/{action_id}/cancel", response_model=ActionStateResponse)
def cancel(
    action_id: UUID,
    body: ActionConversationRequest,
    request: Request,
    identity: InfoTechIdentity,
) -> ActionStateResponse:
    try:
        action = request.app.state.infotech_pending_actions.cancel(action_id, identity.employee_id, body.conversation_id)
    except PendingActionError as exc:
        raise _error(exc) from exc
    return ActionStateResponse(action_id=action.action_id, state=action.state, message="Pending action was cancelled.", conversation_id=body.conversation_id, request_id=request_id_context.get())
