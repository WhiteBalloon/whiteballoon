"""CLI helper to promote a comment into a help request."""

from __future__ import annotations

import argparse
import json
import sys

from sqlmodel import Session, select

from app.db import get_engine
from app.models import RequestComment, User
from app.services import comment_request_promotion_service


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.tools.comment_promotion_cli",
        description="Promote an existing request comment into a HelpRequest.",
    )
    parser.add_argument("--comment-id", type=int, required=True, help="ID of the comment to promote")
    parser.add_argument(
        "--actor",
        default=None,
        help="Username performing the promotion (defaults to the original commenter)",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Optional description override (defaults to the comment body)",
    )
    parser.add_argument(
        "--contact-email",
        default=None,
        help="Optional contact email override (defaults to the comment author's email)",
    )
    parser.add_argument(
        "--status",
        default="open",
        choices=["open", "pending"],
        help="Initial status for the new request",
    )
    parser.add_argument(
        "--source",
        default="cli",
        help="Arbitrary label recorded in logs indicating where the promotion originated",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow multiple requests to be promoted from the same comment",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    engine = get_engine()
    with Session(engine) as session:
        comment = session.get(RequestComment, args.comment_id)
        if not comment:
            parser.error(f"Comment id {args.comment_id} not found")

        if args.actor:
            actor = session.exec(select(User).where(User.username == args.actor)).first()
            if not actor:
                parser.error(f"Actor '{args.actor}' not found")
        else:
            actor = session.get(User, comment.user_id)
            if not actor:
                parser.error("Comment author not found; specify --actor explicitly")

        result = comment_request_promotion_service.promote_comment_to_request(
            session,
            comment_id=args.comment_id,
            actor=actor,
            description=args.description,
            contact_email=args.contact_email,
            status_value=args.status,
            source=args.source,
            allow_duplicate=args.force,
        )

        payload = {
            "request_id": result.help_request.id,
            "comment_id": result.source_comment.id,
            "created_by": result.help_request.created_by_user_id,
            "status": result.help_request.status,
            "actor_username": actor.username,
        }
        print(json.dumps(payload, indent=2))
        return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
