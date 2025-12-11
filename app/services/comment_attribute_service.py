from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, Tuple

from sqlmodel import Session, select

from app.models import CommentAttribute

PROMOTION_QUEUE_KEY = "promotion_queue"


def _now() -> datetime:
    return datetime.utcnow()


def _load_value(value: str | None) -> dict[str, object]:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def get_attribute(session: Session, *, comment_id: int, key: str) -> CommentAttribute | None:
    statement = (
        select(CommentAttribute)
        .where(CommentAttribute.comment_id == comment_id, CommentAttribute.key == key)
        .limit(1)
    )
    return session.exec(statement).first()


def upsert_attribute(
    session: Session,
    *,
    comment_id: int,
    key: str,
    value: dict[str, object],
    acting_user_id: int | None = None,
) -> CommentAttribute:
    payload = json.dumps(value)
    attr = get_attribute(session, comment_id=comment_id, key=key)
    now = _now()
    if attr:
        attr.value = payload
        attr.updated_at = now
        attr.updated_by_user_id = acting_user_id
    else:
        attr = CommentAttribute(
            comment_id=comment_id,
            key=key,
            value=payload,
            created_at=now,
            updated_at=now,
            created_by_user_id=acting_user_id,
            updated_by_user_id=acting_user_id,
        )
    session.add(attr)
    session.commit()
    session.refresh(attr)
    return attr


def queue_promotion_candidate(
    session: Session,
    *,
    comment_id: int,
    reason: str,
    run_id: str,
    metadata: dict[str, object] | None = None,
) -> CommentAttribute:
    attr = get_attribute(session, comment_id=comment_id, key=PROMOTION_QUEUE_KEY)
    existing = _load_value(attr.value if attr else None)
    status = existing.get("status") if isinstance(existing, dict) else None
    if status == "pending":
        return attr  # Already queued
    existing_metadata = existing.get("metadata") if isinstance(existing, dict) else None
    payload = {
        "status": "pending",
        "reason": reason,
        "run_id": run_id,
        "queued_at": _now().isoformat(),
        "attempts": existing.get("attempts", 0) if isinstance(existing, dict) else 0,
        "metadata": metadata if metadata is not None else existing_metadata,
    }
    return upsert_attribute(
        session,
        comment_id=comment_id,
        key=PROMOTION_QUEUE_KEY,
        value=payload,
    )


def list_promotion_attributes(
    session: Session,
    *,
    statuses: Iterable[str] | None = None,
    limit: int | None = None,
) -> list[Tuple[CommentAttribute, dict[str, object]]]:
    statement = select(CommentAttribute).where(CommentAttribute.key == PROMOTION_QUEUE_KEY)
    if limit:
        statement = statement.limit(limit)
    rows = session.exec(statement).all()
    allowed = {status.lower() for status in (statuses or [])}
    results: list[Tuple[CommentAttribute, dict[str, object]]] = []
    for attr in rows:
        payload = _load_value(attr.value)
        status = str(payload.get("status", "")).lower()
        if allowed and status not in allowed:
            continue
        results.append((attr, payload))
    return results


def update_promotion_status(
    session: Session,
    *,
    attribute_id: int,
    status: str,
    **extra: object,
) -> None:
    attr = session.get(CommentAttribute, attribute_id)
    if not attr:
        return
    payload = _load_value(attr.value)
    payload.update(extra)
    payload["status"] = status
    payload["updated_at"] = _now().isoformat()
    attr.value = json.dumps(payload)
    attr.updated_at = _now()
    session.add(attr)
    session.commit()


def reset_promotion_status(
    session: Session,
    *,
    attribute_id: int,
) -> None:
    attr = session.get(CommentAttribute, attribute_id)
    if not attr:
        return
    payload = _load_value(attr.value)
    payload.update(
        {
            "status": "pending",
            "queued_at": _now().isoformat(),
            "attempts": payload.get("attempts", 0),
        }
    )
    attr.value = json.dumps(payload)
    attr.updated_at = _now()
    session.add(attr)
    session.commit()
