"""Explicit, development-only cleanup for narrowly identified demo records.

This module is never imported by application startup or normal seeding.  It
intentionally removes only exact, known Phase 6 diagnostic chat messages and
does not delete conversations, participants, employees, leave, audit, or
idempotency records.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.db.session import SessionLocal
from app.models.chat import ChatMessage


KNOWN_PHASE6_CHAT_MESSAGES = frozenset(
    {
        "Phase 6 live chat verification",
        "Phase 6 final WebSocket verification",
        "Phase 6 diagnostic WebSocket verification",
        "Phase 6 WS diagnostic",
        "Phase 6 send error diagnostic",
    }
)


@dataclass(frozen=True)
class CleanupResult:
    chat_messages: int


def cleanup_known_development_data(session_factory=SessionLocal, *, environment: str | None = None) -> CleanupResult:
    """Remove only the allowlisted development messages from a development DB."""
    active_environment = environment if environment is not None else Settings().environment
    if active_environment != "development":
        raise RuntimeError("Development cleanup is allowed only when ENVIRONMENT=development")

    db = session_factory()
    try:
        removed = (
            db.query(ChatMessage)
            .filter(ChatMessage.content.in_(KNOWN_PHASE6_CHAT_MESSAGES))
            .delete(synchronize_session=False)
        )
        db.commit()
        return CleanupResult(chat_messages=removed)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    result = cleanup_known_development_data()
    print(f"Removed known development chat messages: {result.chat_messages}")


if __name__ == "__main__":
    main()
