from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import time
from threading import Barrier, Thread
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import fakeredis
import httpx
import jwt
import pytest

from app.agents.apply_leave import ApplyLeaveInput
from app.agents.leave_decision import LeaveDecisionInput
from app.core.config import get_settings
from app.services.infotech_ems import EMSUncertainOutcome, InfoTechEMSReadClient
from app.services.infotech_ems import EMSConflict
from app.services.infotech_pending_actions import InfoTechActionName, InfoTechActionState, RedisInfoTechPendingActionStore
from app.services.infotech_pending_actions import PendingActionStateError


ROOT = Path(__file__).resolve().parents[3]
EMS_ROOT = ROOT / "apps/ems-api"
EMS_PYTHON = EMS_ROOT / ".venv/bin/python"
ACTOR = UUID("99999999-9999-4999-8999-999999999991")
MANAGER = UUID("99999999-9999-4999-8999-999999999992")
SECRET = "cross-service-test-secret-with-safe-length"


def _port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def _counts(path):
    with sqlite3.connect(path) as db:
        return tuple(db.execute(f"select count(*) from {t}").fetchone()[0] for t in ("leave_requests", "notifications", "audit_events", "mutation_idempotency"))


class DropCommittedResponse(httpx.BaseTransport):
    def __init__(self): self.inner=httpx.HTTPTransport(); self.keys=[]; self.payloads=[]; self.drop=True
    def handle_request(self, request):
        self.keys.append(request.headers["Idempotency-Key"]); self.payloads.append(request.content)
        response=self.inner.handle_request(request)
        if self.drop:
            self.drop=False; response.close(); raise httpx.ReadTimeout("response lost after commit", request=request)
        return response
    def close(self): self.inner.close()


@pytest.fixture
def ems(tmp_path):
    database=tmp_path / "isolated.sqlite"; port=_port()
    env=os.environ | {"DATABASE_URL":f"sqlite:///{database}","JWT_SECRET":SECRET,"PYTHONPATH":str(EMS_ROOT)}
    setup="""
from uuid import UUID
from app.db.session import Base,engine,SessionLocal
import app.main
from app.models.employee import Employee,Role
from app.core.security import hash_password
Base.metadata.create_all(engine); db=SessionLocal()
m=Employee(id=UUID('99999999-9999-4999-8999-999999999992'),employee_code='XMANAGER',full_name='Manager',company_email='XMANAGER@infotech.local',role=Role.MANAGER,designation='Manager',department='Test',password_hash=hash_password('test-password'),onboarding_completed=True,is_active=True)
e=Employee(id=UUID('99999999-9999-4999-8999-999999999991'),employee_code='XEMPLOYEE',full_name='Employee',company_email='XEMPLOYEE@infotech.local',role=Role.EMPLOYEE,designation='Engineer',department='Test',password_hash=hash_password('test-password'),onboarding_completed=True,is_active=True,manager_id=m.id)
db.add_all([m,e]);db.commit()
"""
    subprocess.run([str(EMS_PYTHON),"-c",setup],cwd=EMS_ROOT,env=env,check=True,capture_output=True,timeout=20)
    proc=subprocess.Popen([str(EMS_PYTHON),"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port)],cwd=EMS_ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health",timeout=.2).status_code==200: break
            except httpx.HTTPError: pass
            time.sleep(.1)
        else: pytest.fail("isolated EMS did not start")
        yield database, f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try: proc.wait(timeout=5)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)


def test_lost_response_recovers_against_real_ems_persistence(ems):
    database, base=ems; store=RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True),execution_lease=timedelta(seconds=1))
    conversation=UUID("99999999-9999-4999-8999-999999999993")
    leave=ApplyLeaveInput(leave_type="CASUAL",start_date="2028-01-15",end_date="2028-01-15",duration="FULL_DAY",reason="cross service recovery")
    action=store.create(actor_employee_id=ACTOR,conversation_id=conversation,tool_name=InfoTechActionName.APPLY_LEAVE,validated_arguments=leave.model_dump(mode="json"),safe_display={"title":"Apply Casual Leave"})
    settings=get_settings().model_copy(update={"ems_api_base_url":base,"ems_jwt_secret":SECRET,"ems_jwt_algorithm":"HS256"})
    token=jwt.encode({"sub":str(ACTOR),"exp":datetime.now(timezone.utc)+timedelta(minutes=5)},SECRET,algorithm="HS256")
    transport=DropCommittedResponse(); claimed=store.claim(action.action_id,ACTOR,conversation)
    with pytest.raises(EMSUncertainOutcome): InfoTechEMSReadClient(settings,httpx.Client(transport=transport)).apply_leave(leave,token,claimed.idempotency_key,"test")
    assert _counts(database)==(1,1,1,1)
    lost=store._load(store._client.get(store._key(action.action_id))); assert lost.state is InfoTechActionState.EXECUTING
    store._client.set(store._key(action.action_id),lost.model_copy(update={"execution_started_at":datetime(2000,1,1,tzinfo=timezone.utc)}).model_dump_json(),keepttl=True)
    recovered=store.claim(action.action_id,ACTOR,conversation)
    retry_transport=DropCommittedResponse(); retry_transport.drop=False
    InfoTechEMSReadClient(settings,httpx.Client(transport=retry_transport)).apply_leave(leave,token,recovered.idempotency_key,"test")
    assert store.finish_succeeded(action.action_id,ACTOR,conversation).state is InfoTechActionState.SUCCEEDED
    assert recovered.idempotency_key==action.idempotency_key and transport.keys==retry_transport.keys==[recovered.idempotency_key]
    assert transport.payloads==retry_transport.payloads==[leave.model_dump_json().encode()] and _counts(database)==(1,1,1,1)
    with sqlite3.connect(database) as db:
        assert db.execute("select leave_type,status,approval_required from leave_requests").fetchone()==("CASUAL","PENDING",1)
        assert db.execute("select source,outcome,operation from audit_events").fetchone()==("AI_AGENT","SUCCEEDED","apply_leave")


def test_concurrent_confirmation_creates_one_real_ems_leave(ems):
    database, base = ems
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True), execution_lease=timedelta(seconds=60))
    conversation = UUID("99999999-9999-4999-8999-999999999994")
    leave = ApplyLeaveInput(leave_type="CASUAL", start_date="2028-01-16", end_date="2028-01-16", duration="FULL_DAY", reason="concurrent recovery")
    action = store.create(actor_employee_id=ACTOR, conversation_id=conversation, tool_name=InfoTechActionName.APPLY_LEAVE, validated_arguments=leave.model_dump(mode="json"), safe_display={"title": "Apply Casual Leave"})
    settings = get_settings().model_copy(update={"ems_api_base_url": base, "ems_jwt_secret": SECRET, "ems_jwt_algorithm": "HS256"})
    token = jwt.encode({"sub": str(ACTOR), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")
    barrier, results = Barrier(3), []

    def contender():
        barrier.wait()
        try:
            claimed = store.claim(action.action_id, ACTOR, conversation)
            InfoTechEMSReadClient(settings, httpx.Client()).apply_leave(leave, token, claimed.idempotency_key, "concurrency")
            results.append(store.finish_succeeded(action.action_id, ACTOR, conversation))
        except Exception as exc:
            results.append(exc)

    one, two = Thread(target=contender), Thread(target=contender)
    one.start(); two.start(); barrier.wait(); one.join(); two.join()
    assert sum(getattr(item, "state", None) is InfoTechActionState.SUCCEEDED for item in results) == 1
    assert sum(isinstance(item, PendingActionStateError) for item in results) == 1
    final = store._load(store._client.get(store._key(action.action_id)))
    assert final.state is InfoTechActionState.SUCCEEDED
    assert final.idempotency_key == action.idempotency_key and final.validated_arguments == leave.model_dump(mode="json")
    assert _counts(database) == (1, 1, 1, 1)


def test_lost_response_recovers_manager_approval_against_real_ems_persistence(ems):
    database, base = ems
    employee_token = jwt.encode({"sub": str(ACTOR), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")
    manager_token = jwt.encode({"sub": str(MANAGER), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")
    created = httpx.post(f"{base}/api/v1/leaves", headers={"Authorization": f"Bearer {employee_token}"}, json={"leave_type": "CASUAL", "start_date": "2028-01-17", "end_date": "2028-01-17", "duration": "FULL_DAY", "reason": "decision recovery"})
    assert created.status_code == 201
    leave_id = UUID(created.json()["id"])
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True), execution_lease=timedelta(seconds=1))
    conversation = UUID("99999999-9999-4999-8999-999999999995")
    decision = LeaveDecisionInput(leave_id=leave_id, decision_note=None)
    action = store.create(actor_employee_id=MANAGER, conversation_id=conversation, tool_name=InfoTechActionName.APPROVE_LEAVE, validated_arguments=decision.model_dump(mode="json"), safe_display={"title": "Approve leave"}, target_entity_id=leave_id)
    settings = get_settings().model_copy(update={"ems_api_base_url": base, "ems_jwt_secret": SECRET, "ems_jwt_algorithm": "HS256"})
    transport = DropCommittedResponse(); claimed = store.claim(action.action_id, MANAGER, conversation)
    with pytest.raises(EMSUncertainOutcome):
        InfoTechEMSReadClient(settings, httpx.Client(transport=transport)).approve_leave(decision, manager_token, claimed.idempotency_key, "test")
    # Initial leave + initial manager notification, then exactly one decision notification/audit/idempotency.
    assert _counts(database) == (1, 2, 1, 1)
    lost = store._load(store._client.get(store._key(action.action_id)))
    store._client.set(store._key(action.action_id), lost.model_copy(update={"execution_started_at": datetime(2000, 1, 1, tzinfo=timezone.utc)}).model_dump_json(), keepttl=True)
    recovered = store.claim(action.action_id, MANAGER, conversation)
    retry = DropCommittedResponse(); retry.drop = False
    InfoTechEMSReadClient(settings, httpx.Client(transport=retry)).approve_leave(decision, manager_token, recovered.idempotency_key, "test")
    assert store.finish_succeeded(action.action_id, MANAGER, conversation).state is InfoTechActionState.SUCCEEDED
    assert transport.keys == retry.keys == [action.idempotency_key] and _counts(database) == (1, 2, 1, 1)
    with sqlite3.connect(database) as db:
        assert db.execute("select status from leave_requests").fetchone() == ("APPROVED",)


def _decision_setup(ems, day: str):
    database, base = ems
    employee_token = jwt.encode({"sub": str(ACTOR), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")
    manager_token = jwt.encode({"sub": str(MANAGER), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)}, SECRET, algorithm="HS256")
    created = httpx.post(f"{base}/api/v1/leaves", headers={"Authorization": f"Bearer {employee_token}"}, json={"leave_type": "CASUAL", "start_date": day, "end_date": day, "duration": "FULL_DAY", "reason": "race test"})
    assert created.status_code == 201
    settings = get_settings().model_copy(update={"ems_api_base_url": base, "ems_jwt_secret": SECRET, "ems_jwt_algorithm": "HS256"})
    return database, base, UUID(created.json()["id"]), manager_token, settings


def _decision_counts(database):
    with sqlite3.connect(database) as db:
        status = db.execute("select status from leave_requests").fetchone()[0]
        notices = db.execute("select count(*) from notifications where title in ('Leave approved','Leave rejected')").fetchone()[0]
        audits = db.execute("select count(*) from audit_events where source='AI_AGENT' and operation in ('approve_leave','reject_leave')").fetchone()[0]
        keys = db.execute("select count(*) from mutation_idempotency where operation in ('approve_leave','reject_leave')").fetchone()[0]
    return status, notices, audits, keys


def test_same_action_decision_concurrency_executes_one_real_approval(ems):
    database, _, leave_id, manager_token, settings = _decision_setup(ems, "2028-01-18")
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True))
    conversation = UUID("99999999-9999-4999-8999-999999999996")
    decision = LeaveDecisionInput(leave_id=leave_id, decision_note=None)
    action = store.create(actor_employee_id=MANAGER, conversation_id=conversation, tool_name=InfoTechActionName.APPROVE_LEAVE, validated_arguments=decision.model_dump(mode="json"), safe_display={"title": "Approve"}, target_entity_id=leave_id)
    barrier, results = Barrier(3), []
    def contender():
        barrier.wait()
        try:
            claimed = store.claim(action.action_id, MANAGER, conversation)
            InfoTechEMSReadClient(settings).approve_leave(decision, manager_token, claimed.idempotency_key, "test")
            results.append(store.finish_succeeded(action.action_id, MANAGER, conversation))
        except Exception as exc: results.append(exc)
    one, two = Thread(target=contender), Thread(target=contender); one.start(); two.start(); barrier.wait(); one.join(); two.join()
    assert sum(getattr(item, "state", None) is InfoTechActionState.SUCCEEDED for item in results) == 1
    assert sum(isinstance(item, PendingActionStateError) for item in results) == 1
    assert _decision_counts(database) == ("APPROVED", 1, 1, 1)
    final = store._load(store._client.get(store._key(action.action_id)))
    assert final.state is InfoTechActionState.SUCCEEDED and final.validated_arguments == decision.model_dump(mode="json") and final.idempotency_key == action.idempotency_key
    with pytest.raises(PendingActionStateError): store.claim(action.action_id, MANAGER, conversation)
    assert _decision_counts(database) == ("APPROVED", 1, 1, 1)


def test_approve_vs_reject_race_has_one_authoritative_ems_winner(ems):
    database, _, leave_id, manager_token, settings = _decision_setup(ems, "2028-01-19")
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True)); conversation = UUID("99999999-9999-4999-8999-999999999997")
    decision = LeaveDecisionInput(leave_id=leave_id, decision_note=None)
    approve = store.create(actor_employee_id=MANAGER, conversation_id=conversation, tool_name=InfoTechActionName.APPROVE_LEAVE, validated_arguments=decision.model_dump(mode="json"), safe_display={"title":"Approve"}, target_entity_id=leave_id)
    reject = store.create(actor_employee_id=MANAGER, conversation_id=conversation, tool_name=InfoTechActionName.REJECT_LEAVE, validated_arguments=decision.model_dump(mode="json"), safe_display={"title":"Reject"}, target_entity_id=leave_id)
    barrier, results = Barrier(3), []
    def contender(action, method):
        barrier.wait()
        try:
            claimed = store.claim(action.action_id, MANAGER, conversation); getattr(InfoTechEMSReadClient(settings), method)(decision, manager_token, claimed.idempotency_key, "test"); results.append((action, store.finish_succeeded(action.action_id, MANAGER, conversation)))
        except EMSConflict:
            results.append((action, store.finish_failed(action.action_id, MANAGER, conversation)))
    one, two = Thread(target=contender, args=(approve,"approve_leave")), Thread(target=contender, args=(reject,"reject_leave")); one.start(); two.start(); barrier.wait(); one.join(); two.join()
    assert _decision_counts(database)[0] in {"APPROVED", "REJECTED"} and _decision_counts(database)[1:] == (1,1,1)
    assert sum(state.state is InfoTechActionState.SUCCEEDED for _, state in results) == 1
    assert sum(state.state is InfoTechActionState.FAILED for _, state in results) == 1


def test_normal_ui_decision_makes_agent_action_stale_without_agent_effects(ems):
    database, base, leave_id, manager_token, settings = _decision_setup(ems, "2028-01-20")
    store = RedisInfoTechPendingActionStore(fakeredis.FakeRedis(decode_responses=True)); conversation = UUID("99999999-9999-4999-8999-999999999998")
    decision = LeaveDecisionInput(leave_id=leave_id, decision_note=None)
    action = store.create(actor_employee_id=MANAGER, conversation_id=conversation, tool_name=InfoTechActionName.APPROVE_LEAVE, validated_arguments=decision.model_dump(mode="json"), safe_display={"title":"Approve"}, target_entity_id=leave_id)
    ui = httpx.post(f"{base}/api/v1/leaves/{leave_id}/reject", headers={"Authorization": f"Bearer {manager_token}"}, json={})
    assert ui.status_code == 200
    claimed = store.claim(action.action_id, MANAGER, conversation)
    with pytest.raises(EMSConflict): InfoTechEMSReadClient(settings).approve_leave(decision, manager_token, claimed.idempotency_key, "test")
    assert store.finish_failed(action.action_id, MANAGER, conversation).state is InfoTechActionState.FAILED
    assert _decision_counts(database) == ("REJECTED", 1, 0, 0)
