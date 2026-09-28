"""Short-lived, single-use WebSocket authentication tickets."""

from __future__ import annotations

import hashlib
import secrets
from uuid import UUID

import redis


class WebSocketTicketError(RuntimeError):
    """A ticket is invalid, expired, consumed, or unavailable."""


class RedisWebSocketTicketStore:
    """Store only hashed opaque tickets; Redis GETDEL makes consumption atomic."""

    def __init__(self, client: redis.Redis, ttl_seconds: int) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @staticmethod
    def _key(ticket: str) -> str:
        digest = hashlib.sha256(ticket.encode("utf-8")).hexdigest()
        return f"ems:ws-ticket:{digest}"

    def issue(self, employee_id: UUID) -> str:
        ticket = secrets.token_urlsafe(32)
        try:
            if not self._client.set(self._key(ticket), str(employee_id), ex=self._ttl_seconds, nx=True):
                raise WebSocketTicketError("WebSocket authentication is unavailable")
        except redis.RedisError as exc:
            raise WebSocketTicketError("WebSocket authentication is unavailable") from exc
        return ticket

    def consume(self, ticket: str) -> UUID:
        try:
            employee_id = self._client.getdel(self._key(ticket))
        except redis.RedisError as exc:
            raise WebSocketTicketError("WebSocket authentication is unavailable") from exc
        if not employee_id:
            raise WebSocketTicketError("WebSocket ticket is invalid or expired")
        try:
            return UUID(str(employee_id))
        except ValueError as exc:
            raise WebSocketTicketError("WebSocket ticket is invalid or expired") from exc
