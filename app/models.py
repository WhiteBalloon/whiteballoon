from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from uuid import uuid4
import secrets

from sqlalchemy import Column, Enum as SAEnum, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(sa_column=Column(String, unique=True, index=True))
    is_admin: bool = Field(default=False, nullable=False)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    sync_scope: str = Field(default="private", sa_column=Column(String, nullable=False, default="private"))



class UserSession(SQLModel, table=True):
    __tablename__ = "sessions"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(days=14))
    last_seen_at: Optional[datetime] = Field(default=None)
    auth_request_id: Optional[str] = Field(default=None, foreign_key="auth_requests.id")
    is_fully_authenticated: bool = Field(default=False, nullable=False)



class HelpRequest(SQLModel, table=True):
    __tablename__ = "help_requests"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: Optional[str] = Field(default=None, max_length=200)
    description: str = Field(default="", max_length=4000)
    status: str = Field(default="open", index=True, nullable=False)
    contact_email: Optional[str] = Field(default=None, max_length=255)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    completed_at: Optional[datetime] = Field(default=None)
    sync_scope: str = Field(default="private", sa_column=Column(String, nullable=False, default="private"))



class RequestComment(SQLModel, table=True):
    __tablename__ = "request_comments"

    id: Optional[int] = Field(default=None, primary_key=True)
    help_request_id: int = Field(foreign_key="help_requests.id", nullable=False, index=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    body: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)
    sync_scope: str = Field(default="private", sa_column=Column(String, nullable=False, default="private"))


class CommentPromotion(SQLModel, table=True):
    __tablename__ = "comment_promotions"

    id: Optional[int] = Field(default=None, primary_key=True)
    comment_id: int = Field(foreign_key="request_comments.id", nullable=False, index=True)
    request_id: int = Field(foreign_key="help_requests.id", nullable=False, index=True)
    created_by_user_id: int = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class CommentAttribute(SQLModel, table=True):
    __tablename__ = "comment_attributes"
    __table_args__ = (UniqueConstraint("comment_id", "key", name="ux_comment_attributes_comment_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    comment_id: int = Field(foreign_key="request_comments.id", nullable=False, index=True)
    key: str = Field(sa_column=Column(String, nullable=False))
    value: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    updated_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")


def _generate_invite_token() -> str:
    return secrets.token_hex(3)


class InviteToken(SQLModel, table=True):
    __tablename__ = "invite_tokens"

    token: str = Field(default_factory=_generate_invite_token, primary_key=True)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    expires_at: Optional[datetime] = Field(default=None)
    max_uses: int = Field(default=1, nullable=False)
    use_count: int = Field(default=0, nullable=False)
    disabled: bool = Field(default=False, nullable=False)
    auto_approve: bool = Field(default=True, nullable=False)
    suggested_username: Optional[str] = Field(default=None, max_length=64)
    suggested_bio: Optional[str] = Field(default=None, max_length=512)
    sync_scope: str = Field(default="private", sa_column=Column(String, nullable=False, default="private"))



class InvitePersonalization(SQLModel, table=True):
    __tablename__ = "invite_personalizations"

    token: str = Field(primary_key=True, foreign_key="invite_tokens.token")
    photo_url: Optional[str] = Field(default=None, max_length=512)
    gratitude_note: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    support_message: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    help_examples: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    fun_details: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)



class UserAttribute(SQLModel, table=True):
    __tablename__ = "user_attributes"
    __table_args__ = (UniqueConstraint("user_id", "key", name="ux_user_attributes_user_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False, index=True)
    key: str = Field(sa_column=Column(String, nullable=False))
    value: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    created_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")
    updated_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id")



class InviteMapCache(SQLModel, table=True):
    __tablename__ = "invite_map_cache"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    payload: str = Field(sa_column=Column(Text, nullable=False))
    version: str = Field(default="v1", sa_column=Column(String(16), nullable=False))
    generated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)



class AuthRequestStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    denied = "denied"
    expired = "expired"


class AuthenticationRequest(SQLModel, table=True):
    __tablename__ = "auth_requests"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    user_id: int = Field(foreign_key="users.id", nullable=False)
    status: AuthRequestStatus = Field(default=AuthRequestStatus.pending, sa_column=Column(SAEnum(AuthRequestStatus)))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    expires_at: datetime = Field(default_factory=lambda: datetime.utcnow() + timedelta(minutes=15))
    verification_code: str = Field(default_factory=lambda: uuid4().hex[:6].upper(), nullable=False)
    device_info: Optional[str] = Field(default=None, max_length=255)
    ip_address: Optional[str] = Field(default=None, max_length=45)



class AuthApproval(SQLModel, table=True):
    __tablename__ = "auth_approvals"

    id: str = Field(default_factory=lambda: uuid4().hex, primary_key=True)
    auth_request_id: str = Field(foreign_key="auth_requests.id", nullable=False)
    approver_user_id: int = Field(foreign_key="users.id", nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)



class Vouch(SQLModel, table=True):
    __tablename__ = "vouches"
    __table_args__ = (UniqueConstraint("voucher_user_id", "subject_user_id", name="ux_vouches_unique"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    voucher_user_id: int = Field(foreign_key="users.id", nullable=False)
    subject_user_id: int = Field(foreign_key="users.id", nullable=False)
    signature: Optional[str] = Field(default=None, max_length=128)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)



class UserProfileHighlight(SQLModel, table=True):
    __tablename__ = "user_profile_highlights"

    user_id: int = Field(primary_key=True, foreign_key="users.id")
    bio_text: str = Field(sa_column=Column(Text, nullable=False))
    proof_points_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    quotes_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    confidence_note: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    source_group: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    snapshot_hash: str = Field(sa_column=Column(String(128), nullable=False))
    snapshot_last_seen_at: datetime = Field(nullable=False)
    llm_model: Optional[str] = Field(default=None, sa_column=Column(String(128)))
    guardrail_issues_json: str = Field(sa_column=Column(Text, nullable=False, default="[]"))
    generated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    stale_after: Optional[datetime] = Field(default=None)
    is_stale: bool = Field(default=False, nullable=False)
    stale_reason: Optional[str] = Field(default=None, sa_column=Column(String(255)))
    manual_override: bool = Field(default=False, nullable=False)
    override_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
