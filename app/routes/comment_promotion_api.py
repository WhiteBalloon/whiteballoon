from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import SessionDep, SessionUser, require_session_user
from app.modules.requests.routes import RequestResponse, calculate_can_complete
from app.services import comment_request_promotion_service

router = APIRouter(prefix="/api/comments", tags=["comments"])


class CommentPromotionPayload(BaseModel):
    description: str | None = None
    contact_email: str | None = None
    status: str | None = None
    force: bool = False


@router.post("/{comment_id}/promote", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
def promote_comment(
    comment_id: int,
    db: SessionDep,
    payload: CommentPromotionPayload = Body(default_factory=CommentPromotionPayload),
    session_user: SessionUser = Depends(require_session_user),
) -> RequestResponse:
    if not session_user.session.is_fully_authenticated:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Fully authenticated session required")

    result = comment_request_promotion_service.promote_comment_to_request(
        db,
        comment_id=comment_id,
        actor=session_user.user,
        description=payload.description,
        contact_email=payload.contact_email,
        status_value=payload.status,
        source="ui",
        allow_duplicate=payload.force,
    )

    return RequestResponse.from_model(
        result.help_request,
        created_by_username=result.comment_author.username,
        can_complete=calculate_can_complete(result.help_request, session_user.user),
    )
