"""SQLAlchemy session event listeners that auto-record DML changes.

Strategy:
- before_flush  : capture UPDATE old-values (via attr history) and DELETE full rows while
                  objects are still in memory; store INSERT objects + pre-serialised data
                  so we don't need to access expired attributes later.
- after_flush_postexec : IDs are now populated on inserted objects; create AuditLog rows
                         and add them to the session (flushed on commit).
- after_commit  : trim the table to MAX_AUDIT_ENTRIES via a separate sync connection.
- after_rollback: clear any pending audit state so it doesn't bleed into the next txn.

Module-level imports ensure AuditLog is registered in Base.metadata at startup.
"""
from __future__ import annotations

import datetime
import enum
import json
import logging
from decimal import Decimal
from typing import Any

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, UOWTransaction

from kaleta.db.base import Base
from kaleta.models.audit_log import AuditLog  # registers table in Base.metadata

log = logging.getLogger(__name__)

# Tables we never audit (prevents infinite recursion and noise).
_SKIP_TABLES: frozenset[str] = frozenset({"audit_log"})


# ── Serialisation helpers ─────────────────────────────────────────────────────

def _jsonify(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.isoformat()
    if isinstance(val, datetime.date):
        return val.isoformat()
    if isinstance(val, Decimal):
        return str(val)
    if isinstance(val, enum.Enum):
        return val.value
    return val


def _serialize(obj: Any) -> dict[str, Any]:
    try:
        return {c.name: _jsonify(getattr(obj, c.name, None)) for c in obj.__table__.columns}
    except Exception:
        return {}


def _is_auditable(obj: Any) -> bool:
    return isinstance(obj, Base) and getattr(obj, "__tablename__", None) not in _SKIP_TABLES


# ── Event listeners ───────────────────────────────────────────────────────────

@event.listens_for(Session, "before_flush")
def _before_flush(session: Session, flush_ctx: UOWTransaction, instances: Any) -> None:
    for obj in session.new:
        if not _is_auditable(obj):
            continue
        # Serialise now while attributes are in memory; id is None — filled post-flush.
        session.info.setdefault("_audit_inserts", []).append((obj, _serialize(obj)))

    for obj in session.dirty:
        if not _is_auditable(obj):
            continue
        insp = sa_inspect(obj)
        old: dict[str, Any] = {}
        new: dict[str, Any] = {}
        for attr in insp.attrs:
            hist = attr.history
            if not hist.has_changes():
                continue
            if hist.deleted:
                old[attr.key] = _jsonify(hist.deleted[0])
            if hist.added:
                new[attr.key] = _jsonify(hist.added[0])
        if old or new:
            identity = insp.identity
            session.info.setdefault("_audit_updates", []).append({
                "table_name": obj.__tablename__,
                "record_id": identity[0] if identity else None,
                "old_data": json.dumps(old),
                "new_data": json.dumps(new),
            })

    for obj in session.deleted:
        if not _is_auditable(obj):
            continue
        insp = sa_inspect(obj)
        identity = insp.identity
        session.info.setdefault("_audit_deletes", []).append({
            "table_name": obj.__tablename__,
            "record_id": identity[0] if identity else None,
            "old_data": json.dumps(_serialize(obj)),
        })


@event.listens_for(Session, "after_flush_postexec")
def _after_flush_postexec(session: Session, flush_ctx: UOWTransaction) -> None:
    entries: list[AuditLog] = []

    for obj, data in session.info.pop("_audit_inserts", []):
        record_id = getattr(obj, "id", None)  # PK survives attribute expiry
        data["id"] = record_id
        entries.append(AuditLog(
            operation="INSERT",
            table_name=obj.__tablename__,
            record_id=record_id,
            old_data=None,
            new_data=json.dumps(data),
        ))

    for d in session.info.pop("_audit_updates", []):
        entries.append(AuditLog(operation="UPDATE", **d))

    for d in session.info.pop("_audit_deletes", []):
        entries.append(AuditLog(operation="DELETE", **d))

    for entry in entries:
        session.add(entry)


@event.listens_for(Session, "after_rollback")
def _after_rollback(session: Session) -> None:
    session.info.pop("_audit_inserts", None)
    session.info.pop("_audit_updates", None)
    session.info.pop("_audit_deletes", None)
