from __future__ import annotations

from datetime import date, datetime, time, timezone
from threading import Barrier, Event, Lock, Thread

from app.agents.models import ExecutionContext
from app.agents.planner import DeterministicPlanner
from app.agents.service import AgentService
from app.schemas.agent import AgentStatus, ConfirmationRequest, PendingActionStatus
from app.schemas.rag import RAGAnswer
from app.schemas.workforce import AttendanceRegularizationExecutionResponse, LeaveExecutionResponse
from app.services.pending_actions import PendingActionStore
from app.tools.actions import RegularizeAttendanceTool, RequestLeaveTool
from app.tools.rag_tool import PolicyAnswerTool
from app.tools.registry import ToolRegistry


class _Rag:
    def answer(self, question: str) -> RAGAnswer:
        return RAGAnswer(answer="unused")


class BlockingActionProvider:
    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self._lock = Lock()
        self.leave_calls = 0
        self.regularization_calls = 0
        self.idempotency_keys: list[str] = []

    def _block(self, kind: str, key: str) -> None:
        with self._lock:
            if kind == "leave": self.leave_calls += 1
            else: self.regularization_calls += 1
            self.idempotency_keys.append(key)
        self.entered.set()
        assert self.release.wait(5), "test did not release the claimed execution"

    def request_leave(self, employee_id, idempotency_key, leave_type, start_date, end_date, reason, request_id=None):
        self._block("leave", idempotency_key)
        return LeaveExecutionResponse(leave_request_id=41, status="PENDING", leave_type=leave_type, start_date=start_date, end_date=end_date, applied_at=datetime.now(timezone.utc), idempotent_replay=False)

    def regularize_attendance(self, employee_id, idempotency_key, attendance_id, requested_in_time, requested_out_time, reason, request_id=None):
        self._block("regularization", idempotency_key)
        return AttendanceRegularizationExecutionResponse(regularization_request_id=42, attendance_id=attendance_id, requested_in_time=requested_in_time, requested_out_time=requested_out_time, status="PENDING", requested_at=datetime.now(timezone.utc), idempotent_replay=False)


def _context() -> ExecutionContext:
    from uuid import uuid4
    return ExecutionContext("EMP001", "Employee", frozenset({"employee"}), "request-1", uuid4(), "EMP001")


def _agent(provider: BlockingActionProvider) -> tuple[AgentService, PendingActionStore]:
    store = PendingActionStore()
    registry = ToolRegistry([PolicyAnswerTool(_Rag()), RequestLeaveTool(store), RegularizeAttendanceTool(store)])
    return AgentService(DeterministicPlanner(), registry, store, provider), store


def _confirm_twice(agent: AgentService, request: ConfirmationRequest, context: ExecutionContext, provider: BlockingActionProvider):
    barrier = Barrier(3)
    outcomes = []
    outcome_lock = Lock()
    def run() -> None:
        barrier.wait()
        result = agent.confirm(request, context)
        with outcome_lock: outcomes.append(result)
    first, second = Thread(target=run), Thread(target=run)
    first.start(); second.start(); barrier.wait()
    assert provider.entered.wait(5), "no provider execution was claimed"
    provider.release.set()
    first.join(5); second.join(5)
    assert not first.is_alive() and not second.is_alive()
    return outcomes


def test_concurrent_leave_confirmation_executes_once():
    provider = BlockingActionProvider(); agent, store = _agent(provider); context = _context()
    _, proposal = agent.registry.execute(__import__("app.schemas.agent", fromlist=["ToolInvocation"]).ToolInvocation(tool_name="request_leave", arguments={"leave_type": "CASUAL", "start_date": "2026-10-01", "end_date": "2026-10-02", "reason": "private"}), context)
    action = proposal.pending_action
    outcomes = _confirm_twice(agent, ConfirmationRequest(action_id=action.action_id, conversation_id=context.conversation_id), context, provider)
    assert provider.leave_calls == 1 and provider.idempotency_keys == [f"agent-action-{action.action_id}"]
    assert sum(item.status is AgentStatus.SUCCEEDED for item in outcomes) == 1
    assert store._actions[action.action_id].status is PendingActionStatus.SUCCEEDED


def test_concurrent_regularization_confirmation_executes_once():
    provider = BlockingActionProvider(); agent, store = _agent(provider); context = _context()
    from app.schemas.agent import ToolInvocation
    _, proposal = agent.registry.execute(ToolInvocation(tool_name="regularize_attendance", arguments={"attendance_id": 7, "requested_in_time": "09:00:00", "requested_out_time": "17:00:00", "reason": "private"}), context)
    action = proposal.pending_action
    outcomes = _confirm_twice(agent, ConfirmationRequest(action_id=action.action_id, conversation_id=context.conversation_id), context, provider)
    assert provider.regularization_calls == 1 and provider.idempotency_keys == [f"agent-action-{action.action_id}"]
    assert sum(item.status is AgentStatus.SUCCEEDED for item in outcomes) == 1
    assert store._actions[action.action_id].status is PendingActionStatus.SUCCEEDED
