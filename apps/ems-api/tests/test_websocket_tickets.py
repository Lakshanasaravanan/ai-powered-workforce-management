from uuid import uuid4

import pytest

from app.services.websocket_tickets import RedisWebSocketTicketStore, WebSocketTicketError


class MemoryRedis:
    def __init__(self):
        self.values = {}

    def set(self, key, value, *, ex, nx):
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def getdel(self, key):
        return self.values.pop(key, None)


def test_ticket_is_opaque_hashed_and_single_use():
    backend = MemoryRedis()
    store = RedisWebSocketTicketStore(backend, ttl_seconds=60)
    employee_id = uuid4()
    ticket = store.issue(employee_id)
    assert all(ticket not in key for key in backend.values)
    assert store.consume(ticket) == employee_id
    with pytest.raises(WebSocketTicketError):
        store.consume(ticket)
