"""Dedicated Phase 20 route-level regressions for persistent Agent workflows."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import fakeredis
import httpx
import jwt

from app.core.config import get_settings
from app.core.ems_auth import EMSIdentityVerifier
from app.rag.index_lifecycle import IndexStatus
from app.schemas.rag import RAGAnswer
from app.services.infotech_conversations import RedisAgentConversationStore
from app.services.infotech_pending_actions import RedisInfoTechPendingActionStore


SECRET = "ems-test-secret-not-for-production-32-bytes"
EMPLOYEE = UUID("10000000-0000-4000-8000-000000000001")
MANAGER = UUID("10000000-0000-4000-8000-000000000002")
ADMIN = UUID("10000000-0000-4000-8000-000000000003")
REPORT = UUID("10000000-0000-4000-8000-000000000004")


def _token(subject: UUID) -> str:
    return jwt.encode({"sub": str(subject), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")


def _headers(subject: UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(subject)}"}


def _profile(employee_id: UUID, role: str, code: str) -> dict:
    return {"id": str(employee_id), "employee_code": code, "full_name": code, "company_email": f"{code}@infotech.local", "role": role, "designation": "Engineer", "department": "Engineering", "manager_id": None, "is_active": True}


class EMS:
    def __init__(self): self.applies: list[object] = []; self.attendance: list[tuple[UUID | None, date, date]] = []; self.payroll: list[tuple[str, UUID, int, int | None]] = []
    def get_working_day(self, day, _): return SimpleNamespace(is_working_day=True, reason=None)
    def apply_leave(self, leave, *_): self.applies.append(leave); return SimpleNamespace()
    def search_employees(self, code, _):
        rows = {"INF1001": _profile(EMPLOYEE,"EMPLOYEE","INF1001"), "INF1002": _profile(MANAGER,"MANAGER","INF1002"), "INF1003": _profile(REPORT,"EMPLOYEE","INF1003")}
        return [SimpleNamespace(**row) for key, row in rows.items() if key == code]
    def get_attendance(self, employee_id, start, end, _):
        self.attendance.append((employee_id, start, end)); return {"records":[{"status":"PRESENT","late_minutes":0,"worked_minutes":480}]}
    def get_payroll_preview(self, employee_id, year, month, _): self.payroll.append(("preview",employee_id,year,month)); return {"payroll_year":year,"payroll_month":month,"payable_salary":"100"}
    def get_finalized_payroll(self, employee_id, year, month, _): self.payroll.append(("finalized",employee_id,year,month)); return {"payroll_year":year,"payroll_month":month,"payable_salary":"100"}
    def get_finalized_payroll_history(self, employee_id, _): self.payroll.append(("history",employee_id,0,None)); return []


class RAG:
    def __init__(self): self.questions=[]
    def answer(self, question): self.questions.append(question); return RAGAnswer(answer="grounded", sources=[])


def setup(client):
    roles={str(EMPLOYEE):("EMPLOYEE","INF1001"),str(MANAGER):("MANAGER","INF1002"),str(ADMIN):("ADMIN","ADM001"),str(REPORT):("EMPLOYEE","INF1003")}
    def identity(request):
        subject=jwt.decode(request.headers["Authorization"].split()[1], SECRET, algorithms=["HS256"])["sub"]
        role,code=roles[subject]; return httpx.Response(200,json=_profile(UUID(subject),role,code))
    settings=get_settings(); client.app.state.ems_identity_verifier=EMSIdentityVerifier(settings,client=httpx.Client(transport=httpx.MockTransport(identity)))
    ems=EMS(); client.app.state.infotech_ems_client=ems
    redis=fakeredis.FakeRedis(decode_responses=True); client.app.state.infotech_conversations=RedisAgentConversationStore(redis); client.app.state.infotech_pending_actions=RedisInfoTechPendingActionStore(redis)
    client.app.state.rag_service=RAG(); client.app.state.rag_index_status=IndexStatus(True)
    return ems


def test_exact_four_turn_leave_flow_correction_and_duplicate_confirmation(client):
    ems=setup(client); conversation=str(uuid4())
    first=client.post("/api/v1/agent/query",json={"message":"apply leave for tomorrow","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert first.status_code==200 and "leave type" in first.json()["answer"].lower()
    second=client.post("/api/v1/agent/query",json={"message":"medical","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert second.status_code==200 and "reason" in second.json()["answer"].lower() and not ems.applies
    third=client.post("/api/v1/agent/query",json={"message":"fever","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert third.json()["response_type"]=="action_proposal" and not ems.applies
    confirmed=client.post("/api/v1/agent/query",json={"message":"confirm","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert confirmed.status_code==200 and len(ems.applies)==1 and ems.applies[0].leave_type=="MEDICAL"
    replay=client.post("/api/v1/agent/query",json={"message":"confirm","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert replay.status_code==200 and len(ems.applies)==1


def test_correction_invalidates_proposal_and_cancel_does_not_execute(client):
    ems=setup(client); conversation=str(uuid4())
    client.post("/api/v1/agent/query",json={"message":"apply leave tomorrow","conversation_id":conversation},headers=_headers(EMPLOYEE))
    client.post("/api/v1/agent/query",json={"message":"medical","conversation_id":conversation},headers=_headers(EMPLOYEE))
    proposal=client.post("/api/v1/agent/query",json={"message":"fever","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert proposal.json()["response_type"]=="action_proposal"
    corrected=client.post("/api/v1/agent/query",json={"message":"actually make it emergency","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert corrected.json()["response_type"]=="action_proposal" and not ems.applies
    client.post("/api/v1/agent/query",json={"message":"cancel","conversation_id":conversation},headers=_headers(EMPLOYEE)); assert not ems.applies


def test_attendance_rbac_and_context_follow_up_use_ems(client):
    ems=setup(client); conversation=str(uuid4())
    assert client.post("/api/v1/agent/query",json={"message":"How was my attendance this month?","conversation_id":conversation},headers=_headers(EMPLOYEE)).status_code==200
    assert client.post("/api/v1/agent/query",json={"message":"What about last month?","conversation_id":conversation},headers=_headers(EMPLOYEE)).status_code==200
    assert len(ems.attendance)==2 and ems.attendance[0][0] is None
    assert client.post("/api/v1/agent/query",json={"message":"Show INF1003 attendance this month","conversation_id":str(uuid4())},headers=_headers(MANAGER)).status_code==200
    assert client.post("/api/v1/agent/query",json={"message":"Show INF1002 attendance this month","conversation_id":str(uuid4())},headers=_headers(ADMIN)).status_code==200
    denied=client.post("/api/v1/agent/query",json={"message":"Show INF1003 attendance this month","conversation_id":str(uuid4())},headers=_headers(EMPLOYEE)); assert denied.status_code==200


def test_payroll_is_admin_only_and_context_keeps_operation(client):
    ems=setup(client); conversation=str(uuid4())
    preview=client.post("/api/v1/agent/query",json={"message":"Show payroll preview for INF1001 for August 2026.","conversation_id":conversation},headers=_headers(ADMIN)); assert preview.status_code==200
    follow=client.post("/api/v1/agent/query",json={"message":"What about July?","conversation_id":conversation},headers=_headers(ADMIN)); assert follow.status_code==200
    finalized=client.post("/api/v1/agent/query",json={"message":"Show finalized payroll for INF1001 for August 2026.","conversation_id":str(uuid4())},headers=_headers(ADMIN)); assert finalized.status_code==200
    finalized_follow=client.post("/api/v1/agent/query",json={"message":"What about July?","conversation_id":finalized.json()["conversation_id"]},headers=_headers(ADMIN)); assert finalized_follow.status_code==200
    history=client.post("/api/v1/agent/query",json={"message":"List finalized payroll history for INF1001.","conversation_id":str(uuid4())},headers=_headers(ADMIN)); assert history.status_code==200
    denied=client.post("/api/v1/agent/query",json={"message":"Show payroll preview for INF1001 for August 2026.","conversation_id":str(uuid4())},headers=_headers(EMPLOYEE)); assert "only to Administrators" in denied.json()["answer"] and "100" not in denied.json()["answer"]
    assert {item[0] for item in ems.payroll} >= {"preview","finalized","history"}
    assert ems.payroll[-2][0] == "finalized"
