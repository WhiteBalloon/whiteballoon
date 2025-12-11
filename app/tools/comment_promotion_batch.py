"""Batch promotion worker for request-like comments."""

from __future__ import annotations

import argparse
import json
from typing import Iterable

from fastapi import HTTPException
from sqlmodel import Session

from app.db import get_engine
from app.models import CommentAttribute, RequestComment, User
from app.services import comment_attribute_service, comment_request_promotion_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.tools.comment_promotion_batch",
        description="Process pending comment promotion queue entries or inspect the queue.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Promote pending queue entries")
    run_parser.add_argument("--limit", type=int, default=20, help="Max pending items to process")
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow promoting comments even if prior attempt succeeded (duplicates)",
    )

    list_parser = subparsers.add_parser("list", help="List queue entries")
    list_parser.add_argument(
        "--status",
        choices=["pending", "completed", "failed", "all"],
        default="pending",
        help="Filter by status",
    )
    list_parser.add_argument("--limit", type=int, default=50)

    retry_parser = subparsers.add_parser("retry", help="Reset an entry back to pending")
    retry_parser.add_argument("attribute_id", type=int, help="Comment attribute row ID")

    return parser


def _load_payload(attr: CommentAttribute) -> dict[str, object]:
    try:
        return json.loads(attr.value or "{}")
    except json.JSONDecodeError:
        return {}


def _list_queue(engine, *, status: str, limit: int) -> None:
    statuses: Iterable[str] | None = None
    if status != "all":
        statuses = [status]
    with Session(engine) as session:
        rows = comment_attribute_service.list_promotion_attributes(
            session, statuses=statuses, limit=limit
        )
    if not rows:
        print("No queue entries found.")
        return
    for attr, payload in rows:
        status_label = payload.get("status")
        reason = payload.get("reason")
        run_id = payload.get("run_id")
        request_id = payload.get("request_id")
        error = payload.get("error")
        print(
            f"#{attr.id} comment={attr.comment_id} status={status_label} reason={reason} run={run_id} "
            f"request={request_id} error={error}"
        )
        metadata = payload.get("metadata")
        if metadata:
            print(f"    metadata: {metadata}")


def _reset_entry(engine, attribute_id: int) -> None:
    with Session(engine) as session:
        comment_attribute_service.reset_promotion_status(session, attribute_id=attribute_id)
    print(f"Reset attribute #{attribute_id} to pending")


def _process_pending(engine, *, limit: int, force: bool) -> int:
    with Session(engine) as session:
        pending = comment_attribute_service.list_promotion_attributes(
            session, statuses=["pending"], limit=limit
        )
    if not pending:
        print("No pending promotion entries.")
        return 0

    processed = 0
    for attr, payload in pending:
        success = _process_single(engine, attr.id, payload, force=force)
        if success:
            processed += 1
    print(f"Processed {processed} / {len(pending)} pending entries.")
    return processed


def _process_single(engine, attribute_id: int, payload: dict[str, object], *, force: bool) -> bool:
    with Session(engine) as session:
        attr = session.get(CommentAttribute, attribute_id)
        if not attr:
            return False
        data = _load_payload(attr)
        status = str(data.get("status", "")).lower()
        if status == "completed" and not force:
            return False
        comment = session.get(RequestComment, attr.comment_id)
        if not comment:
            comment_attribute_service.update_promotion_status(
                session,
                attribute_id=attr.id,
                status="failed",
                error="comment missing",
            )
            return False
        actor = session.get(User, comment.user_id)
        if not actor:
            comment_attribute_service.update_promotion_status(
                session,
                attribute_id=attr.id,
                status="failed",
                error="comment author missing",
            )
            return False
        try:
            result = comment_request_promotion_service.promote_comment_to_request(
                session,
                comment_id=comment.id,
                actor=actor,
                source="indexer",
                allow_duplicate=force,
            )
        except HTTPException as exc:
            comment_attribute_service.update_promotion_status(
                session,
                attribute_id=attr.id,
                status="failed",
                error=str(exc.detail),
                attempts=data.get("attempts", 0) + 1,
            )
            print(f"Failed to promote comment {comment.id}: {exc.detail}")
            return False
        comment_attribute_service.update_promotion_status(
            session,
            attribute_id=attr.id,
            status="completed",
            request_id=result.help_request.id,
            attempts=data.get("attempts", 0) + 1,
        )
        print(f"Promoted comment {comment.id} -> request {result.help_request.id}")
        return True


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    engine = get_engine()

    if args.command == "run":
        _process_pending(engine, limit=args.limit, force=args.force)
        return 0
    if args.command == "list":
        status = args.status
        _list_queue(engine, status=status, limit=args.limit)
        return 0
    if args.command == "retry":
        _reset_entry(engine, attribute_id=args.attribute_id)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
