"""EMS-owned idempotency helpers for consequential mutation endpoints."""
import hashlib
import json

from app.schemas.leaves import LeaveCreate


def leave_fingerprint(body: LeaveCreate) -> str:
    payload = {
        "leave_type": body.leave_type.value,
        "start_date": body.start_date.isoformat(),
        "end_date": body.end_date.isoformat(),
        "duration": body.duration.value,
        "half_day_period": body.half_day_period.value if body.half_day_period else None,
        "reason": body.reason,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def leave_decision_fingerprint(leave_id, decision_note: str | None) -> str:
    """Canonical decision payload; no requester data or transport metadata."""
    note = " ".join(decision_note.split()) if decision_note else None
    payload = {"leave_id": str(leave_id), "decision_note": note}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
