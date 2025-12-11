from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.models import CommentPromotion, HelpRequest, RequestComment, User
from app.modules.requests import services as request_services

logger = logging.getLogger(__name__)


@dataclass
class CommentPromotionResult:
    help_request: HelpRequest
    source_comment: RequestComment
    comment_author: User
    promotion: CommentPromotion


def get_promotions_for_comment_ids(
    session: Session, comment_ids: list[int]
) -> dict[int, list[CommentPromotion]]:
    if not comment_ids:
        return {}
    stmt = (
        select(CommentPromotion)
        .where(CommentPromotion.comment_id.in_(comment_ids))
        .order_by(CommentPromotion.created_at.asc())
    )
    mapping: dict[int, list[CommentPromotion]] = {}
    for promotion in session.exec(stmt).all():
        mapping.setdefault(promotion.comment_id, []).append(promotion)
    return mapping


def promote_comment_to_request(
    session: Session,
    *,
    comment_id: int,
    actor: User,
    description: Optional[str] = None,
    contact_email: Optional[str] = None,
    status_value: Optional[str] = None,
    source: str = "ui",
    allow_duplicate: bool = False,
) -> CommentPromotionResult:
    """Create a HelpRequest derived from a comment."""
    comment = session.get(RequestComment, comment_id)
    if not comment or comment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    comment_author = session.get(User, comment.user_id)
    if not comment_author:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment author missing")

    summary = (description if description is not None else comment.body or "").strip()
    if not summary:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Description required")

    existing_promotion = session.exec(
        select(CommentPromotion)
        .where(CommentPromotion.comment_id == comment.id)
        .order_by(CommentPromotion.created_at.desc())
    ).first()
    if existing_promotion and not allow_duplicate:
        detail = {
            "message": "Comment already promoted",
            "promoted_request_id": existing_promotion.request_id,
        }
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)

    help_request = request_services.create_request(
        session,
        user=comment_author,
        description=summary,
        contact_email=contact_email or comment_author.contact_email,
        status_value=status_value or "open",
    )

    promotion = CommentPromotion(
        comment_id=comment.id,
        request_id=help_request.id,
        created_by_user_id=actor.id,
    )
    session.add(promotion)
    session.commit()
    session.refresh(promotion)

    logger.info(
        "User %s promoted comment %s from request %s into new request %s (source=%s)",
        actor.id,
        comment.id,
        comment.help_request_id,
        help_request.id,
        source,
    )

    return CommentPromotionResult(
        help_request=help_request,
        source_comment=comment,
        comment_author=comment_author,
        promotion=promotion,
    )
