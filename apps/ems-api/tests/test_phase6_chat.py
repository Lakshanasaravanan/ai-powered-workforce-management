from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.api.routes.chat as chat_route
from app.core.security import hash_password, token
from app.db.session import Base, get_db
from app.main import app
from app.models.employee import Employee, Role
from app.models.notification import Notification, NotificationCategory
from app.services.websocket_tickets import WebSocketTicketError


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Session = sessionmaker(engine)
client = TestClient(app)


class TicketStore:
    ttl_seconds = 60

    def __init__(self):
        self._tickets = {}

    def issue(self, employee_id):
        ticket = uuid4().hex
        self._tickets[ticket] = employee_id
        return ticket

    def consume(self, ticket):
        employee_id = self._tickets.pop(ticket, None)
        if employee_id is None:
            raise WebSocketTicketError("invalid")
        return employee_id

    def expire(self, ticket):
        self._tickets.pop(ticket, None)


def db_override():
    db = Session()
    try:
        yield db
    finally:
        db.close()


def make(code, role=Role.EMPLOYEE, active=True):
    db = Session()
    user = Employee(employee_code=code, full_name=code, company_email=f"{code}@x.test", role=role, designation="x", department="x", password_hash=hash_password("x"), onboarding_completed=True, is_active=active)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def headers(user):
    return {"Authorization": f"Bearer {token(str(user.id))}"}


def setup():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    app.dependency_overrides[get_db] = db_override
    app.state.websocket_ticket_store = TicketStore()
    chat_route.SessionLocal = Session


def issue_ticket(user):
    response = client.post("/api/v1/chat/ws-ticket", headers=headers(user))
    assert response.status_code == 200
    return response.json()["ticket"]


def websocket(ticket):
    return client.websocket_connect(
        "/api/v1/chat/ws",
        subprotocols=[f"infotech.chat.ticket.{ticket}"],
        headers={"origin": "http://localhost:5173"},
    )


def test_direct_membership_messages_unread_and_notifications():
    setup()
    a, b, c, admin = make("A"), make("B"), make("C"), make("ADMIN", Role.ADMIN)
    response = client.post("/api/v1/chat/conversations/direct", json={"target_employee_id": str(b.id)}, headers=headers(a))
    assert response.status_code == 200
    conversation_id = response.json()["id"]
    assert client.post("/api/v1/chat/conversations/direct", json={"target_employee_id": str(a.id)}, headers=headers(b)).json()["id"] == conversation_id
    assert client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers(b)).status_code == 200
    assert client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers(c)).status_code == 404
    assert client.get(f"/api/v1/chat/conversations/{conversation_id}", headers=headers(admin)).status_code == 404
    sent = client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "hello"}, headers=headers(a))
    assert sent.status_code == 200
    assert client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "x"}, headers=headers(c)).status_code == 404
    assert client.get("/api/v1/chat/conversations", headers=headers(b)).json()[0]["unread_count"] == 1
    assert client.post(f"/api/v1/chat/conversations/{conversation_id}/read", headers=headers(b)).status_code == 200
    assert client.get("/api/v1/chat/conversations", headers=headers(b)).json()[0]["unread_count"] == 0
    assert client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "   "}, headers=headers(a)).status_code == 422
    db = Session()
    assert db.query(Notification).filter_by(category=NotificationCategory.CHAT, recipient_id=b.id).count() == 1
    assert db.query(Notification).filter_by(recipient_id=a.id).count() == 0
    db.close()


def test_group_validates_active_members():
    setup()
    a, b, inactive = make("A"), make("B"), make("D", active=False)
    assert client.post("/api/v1/chat/conversations/group", json={"name": "Team", "participant_employee_ids": [str(b.id)]}, headers=headers(a)).status_code == 200
    assert client.post("/api/v1/chat/conversations/group", json={"name": "Bad", "participant_employee_ids": [str(inactive.id)]}, headers=headers(a)).status_code == 422


def test_websocket_ticket_is_authenticated_scoped_single_use_and_not_in_url():
    setup()
    a, b, inactive = make("A"), make("B"), make("I", active=False)
    assert client.post("/api/v1/chat/ws-ticket").status_code in {401, 403}
    ticket = issue_ticket(a)
    with websocket(ticket) as connected:
        connected.send_text("ping")
        assert connected.accepted_subprotocol == f"infotech.chat.ticket.{ticket}"
        assert str(a.id) in chat_route.manager._connections
        assert str(b.id) not in chat_route.manager._connections
    with pytest.raises(Exception):
        with websocket(ticket):
            pass
    with pytest.raises(Exception):
        with websocket("not-a-ticket"):
            pass
    with pytest.raises(Exception):
        with client.websocket_connect(f"/api/v1/chat/ws?token={token(str(a.id))}", headers={"origin": "http://localhost:5173"}):
            pass
    expired = issue_ticket(b)
    app.state.websocket_ticket_store.expire(expired)
    with pytest.raises(Exception):
        with websocket(expired):
            pass
    inactive_ticket = app.state.websocket_ticket_store.issue(inactive.id)
    with pytest.raises(Exception):
        with websocket(inactive_ticket):
            pass
    origin_ticket = issue_ticket(a)
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/chat/ws", subprotocols=[f"infotech.chat.ticket.{origin_ticket}"], headers={"origin": "http://untrusted.test"}):
            pass


def test_websocket_implementation_never_reads_a_query_token_or_builds_one_in_the_client():
    from pathlib import Path

    route_source = Path(chat_route.__file__).read_text(encoding="utf-8")
    client_source = (Path(__file__).resolve().parents[2] / "web" / "src" / "Chat.tsx").read_text(encoding="utf-8")
    assert "query_params.get(\"token\")" not in route_source
    assert "?token=" not in client_source
    assert "infotech.chat.ticket." in client_source


def test_rest_message_broadcasts_only_to_conversation_members():
    setup()
    a, b, c = make("A"), make("B"), make("C")
    conversation_id = client.post("/api/v1/chat/conversations/direct", json={"target_employee_id": str(b.id)}, headers=headers(a)).json()["id"]
    delivered = []

    async def capture(ids, event):
        delivered.append((ids, event))

    original = chat_route.manager.broadcast
    chat_route.manager.broadcast = capture
    try:
        response = client.post(f"/api/v1/chat/conversations/{conversation_id}/messages", json={"content": "private"}, headers=headers(a))
        assert response.status_code == 200
    finally:
        chat_route.manager.broadcast = original
    assert len(delivered) == 1
    recipients, event = delivered[0]
    assert str(b.id) in recipients and str(c.id) not in recipients
    assert event["type"] == "message.created" and event["conversation_id"] == conversation_id and event["message"]["id"] == response.json()["id"]
