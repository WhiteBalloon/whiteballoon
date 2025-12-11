from __future__ import annotations

import logging
import math
import re
from collections import Counter
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import urlencode, urlparse
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import and_, desc, func, literal, or_, union_all
from sqlmodel import Session, select

from app.dependencies import (
    SessionDep,
    SessionUser,
    get_current_session,
    require_authenticated_user,
    require_session_user,
)
from app.models import (
    AuthenticationRequest,
    CommentPromotion,
    HelpRequest,
    RequestComment,
    User,
    UserAttribute,
    UserSession,
)
from app.modules.requests import services as request_services
from app.modules.requests.routes import RequestResponse, calculate_can_complete
from app.services import (
    auth_service,
    comment_llm_insights_service,
    comment_request_promotion_service,
    invite_graph_service,
    invite_map_cache_service,
    request_chat_search_service,
    request_chat_suggestions,
    request_comment_service,
    signal_profile_snapshot_service,
    user_attribute_service,
    user_profile_highlight_service,
    vouch_service,
)
from app import config
from app.url_utils import build_invite_link, generate_qr_code_data_url
from .helpers import describe_session_role, templates

router = APIRouter(tags=["ui"])

logger = logging.getLogger(__name__)

CHAT_SEARCH_MIN_COMMENTS = 5

FILTER_TOPICS = [
    {"slug": "groceries", "label": "Groceries", "keywords": ["grocery", "groceries", "food", "meal", "produce"]},
    {"slug": "rides", "label": "Transportation", "keywords": ["ride", "carpool", "transport", "drive", "pickup"]},
    {"slug": "housing", "label": "Housing", "keywords": ["room", "housing", "shelter", "rent"]},
    {"slug": "health", "label": "Health", "keywords": ["medical", "health", "doctor", "medicine"]},
    {"slug": "childcare", "label": "Childcare", "keywords": ["child", "kid", "babysit", "school"]},
]

FILTER_TOPICS_LOOKUP = {topic["slug"]: topic for topic in FILTER_TOPICS}

URGENCY_LEVELS = [
    {"slug": "urgent", "label": "Urgent", "keywords": ["urgent", "asap", "immediately", "tonight", "today"]},
    {"slug": "soon", "label": "Soon", "keywords": ["tomorrow", "this week", "next few", "soon"]},
    {"slug": "flexible", "label": "Flexible", "keywords": []},
]

STATUS_OPTIONS = [
    {"slug": "open", "label": "Open"},
    {"slug": "completed", "label": "Completed"},
]

STATUS_LOOKUP = {status_option["slug"]: status_option for status_option in STATUS_OPTIONS}

BROWSE_PAGE_SIZE = 12
BROWSE_ALLOWED_TYPES = {"all", "requests", "comments", "profiles"}
BROWSE_TABS = [
    {"slug": "all", "label": "Everything"},
    {"slug": "requests", "label": "Requests"},
    {"slug": "comments", "label": "Comments"},
    {"slug": "profiles", "label": "Profiles"},
]


def _normalize_filter_values(values: list[str]) -> set[str]:
    return {value.strip().lower() for value in values if value and value.strip()}


def _infer_request_topics(help_request: HelpRequest) -> set[str]:
    description = (help_request.description or "").lower()
    topics: set[str] = set()
    for topic in FILTER_TOPICS:
        if any(keyword in description for keyword in topic["keywords"]):
            topics.add(topic["slug"])
    return topics


def _infer_request_urgency(help_request: HelpRequest) -> str:
    description = (help_request.description or "").lower()
    for level in URGENCY_LEVELS:
        if level["keywords"] and any(keyword in description for keyword in level["keywords"]):
            return level["slug"]
    return "flexible"


def _matches_request_filters(
    topics: set[str],
    urgency: str,
    status_value: str,
    topic_filters: set[str],
    urgency_filters: set[str],
    status_filters: set[str],
) -> bool:
    if topic_filters and topics.isdisjoint(topic_filters):
        return False
    if urgency_filters and urgency not in urgency_filters:
        return False
    if status_filters and status_value not in status_filters:
        return False
    return True


def _build_filter_url(
    base_path: str,
    current_items: list[tuple[str, str]],
    field: str,
    value: str,
    active: bool,
) -> str:
    preserved = [
        (key, val) for key, val in current_items if not (key == field and val.lower() == value.lower())
    ]
    preserved = [(k, v) for (k, v) in preserved if k != "page"]
    if not active:
        preserved.append((field, value))
    query = urlencode(preserved, doseq=True)
    return f"{base_path}?{query}" if query else base_path


def _build_reset_url(base_path: str, current_items: list[tuple[str, str]]) -> str:
    filtered = [
        (key, val)
        for key, val in current_items
        if key not in {"topic", "urgency", "status", "page"}
    ]
    query = urlencode(filtered, doseq=True)
    return f"{base_path}?{query}" if query else base_path


def _normalize_search_term(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _sanitize_browse_tab(value: Optional[str]) -> str:
    if not value:
        return "all"
    value = value.strip().lower()
    return value if value in BROWSE_ALLOWED_TYPES else "all"


def _topic_keyword_clause(columns: list, tag_filters: set[str]):  # noqa: ANN001
    if not tag_filters:
        return None
    keywords: list[str] = []
    for slug in tag_filters:
        topic = FILTER_TOPICS_LOOKUP.get(slug)
        if not topic:
            continue
        keywords.extend(topic.get("keywords", []))
    if not keywords:
        return None
    clauses = []
    for column in columns:
        for keyword in keywords:
            clauses.append(column.ilike(f"%{keyword}%"))
    if not clauses:
        return None
    return or_(*clauses)


def _profile_visibility_clause(db: Session, viewer: User):  # noqa: ANN001
    if viewer.is_admin:
        return None

    invitee_ids = user_attribute_service.list_invitee_user_ids(
        db,
        inviter_user_id=viewer.id,
    )
    allowed_ids = {user_id for user_id in invitee_ids if user_id}
    if viewer.id:
        allowed_ids.add(viewer.id)

    if not allowed_ids:
        return User.sync_scope == "public"

    return or_(User.sync_scope == "public", User.id.in_(list(allowed_ids)))


def _build_browse_tab_url(request: Request, tab_slug: str) -> str:
    current_items = list(request.query_params.multi_items()) if hasattr(request.query_params, "multi_items") else list(request.query_params.items())
    filtered = [(key, value) for key, value in current_items if key != "type"]
    if tab_slug != "all":
        filtered.append(("type", tab_slug))
    query = urlencode(filtered, doseq=True)
    return f"{request.url.path}?{query}" if query else request.url.path


def _build_browse_tabs(request: Request, tab_counts: dict[str, int], active_tab: str) -> list[dict[str, object]]:
    tabs: list[dict[str, object]] = []
    for tab in BROWSE_TABS:
        slug = tab["slug"]
        tabs.append(
            {
                "slug": slug,
                "label": tab["label"],
                "count": tab_counts.get(slug, 0),
                "url": _build_browse_tab_url(request, slug),
                "active": slug == active_tab,
            }
        )
    return tabs


def _build_pagination_metadata(request: Request, current_page: int, total_pages: int) -> dict[str, object]:
    total_pages = max(1, total_pages)

    def _page_url(target_page: int) -> Optional[str]:
        if target_page < 1 or target_page > total_pages:
            return None
        url = request.url.include_query_params(page=target_page)
        return str(url)

    return {
        "current": current_page,
        "total": total_pages,
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_url": _page_url(current_page - 1) if current_page > 1 else None,
        "next_url": _page_url(current_page + 1) if current_page < total_pages else None,
    }


def _truncate_text(text: str, limit: int = 220) -> str:
    snippet = (text or "").strip()
    if len(snippet) <= limit:
        return snippet
    trimmed = snippet[: max(0, limit - 3)].rstrip()
    return f"{trimmed}..."


def _serialize_requests(db: Session, items, viewer: Optional[User] = None):
    creator_usernames = request_services.load_creator_usernames(db, items)
    serialized = []
    for item in items:
        can_complete = calculate_can_complete(item, viewer) if viewer else False
        serialized.append(
            RequestResponse.from_model(
                item,
                created_by_username=creator_usernames.get(item.created_by_user_id),
                can_complete=can_complete,
            ).model_dump()
        )
    return serialized


def _format_proof_receipts(proof_points: list[dict[str, str]] | None) -> list[dict[str, object]]:
    receipts: list[dict[str, object]] = []
    if not proof_points:
        return receipts
    for point in proof_points:
        label = str(point.get("label", "")).strip()
        detail = str(point.get("detail", "")).strip()
        reference = str(point.get("reference", "")).strip()
        href: Optional[str] = None
        display_ref = reference
        external = False
        ref_lower = reference.lower()
        if ref_lower.startswith("http"):
            href = reference
            external = True
            parsed = urlparse(reference)
            display_ref = parsed.netloc or reference
        elif ref_lower.startswith("request#"):
            digits = "".join(ch for ch in reference if ch.isdigit())
            if digits:
                href = f"/requests/{digits}"
                display_ref = f"Request #{digits}"
        elif reference.isdigit():
            href = f"/requests/{reference}"
            display_ref = f"Request #{reference}"
        receipts.append(
            {
                "label": label,
                "detail": detail,
                "reference": reference,
                "href": href,
                "display_ref": display_ref,
                "external": external,
            }
        )
    return receipts


def _format_snapshot_links(entries) -> list[dict[str, object]]:  # noqa: ANN001
    links: list[dict[str, object]] = []
    if not entries:
        return links
    for entry in entries:
        url = str(getattr(entry, "url", "") or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        domain = (getattr(entry, "domain", "") or parsed.netloc or url).lower()
        safe_url = parsed.geturl()
        links.append(
            {
                "domain": domain,
                "href": safe_url,
                "count": getattr(entry, "count", 0) or 0,
            }
        )
    return links


def _build_request_ctas(request_ids: list[int], user_id: int) -> list[dict[str, object]]:
    chips: list[dict[str, object]] = []
    seen: set[int] = set()
    for request_id in request_ids:
        if request_id in seen:
            continue
        seen.add(request_id)
        chips.append(
            {
                "request_id": request_id,
                "href": f"/requests/{request_id}?chat_participant={user_id}",
            }
        )
        if len(chips) >= 3:
            break
    return chips

@router.get("/")
def home(
    request: Request,
    db: SessionDep,
    session_record: Optional[UserSession] = Depends(get_current_session),
) -> Response:
    if not session_record:
        return templates.TemplateResponse("auth/logged_out.html", {"request": request})

    user = db.exec(select(User).where(User.id == session_record.user_id)).first()
    if not user:
        response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(auth_service.SESSION_COOKIE_NAME, path="/")
        return response

    session_role = describe_session_role(user, session_record)

    if not session_record.is_fully_authenticated:
        auth_request = None
        if session_record.auth_request_id:
            auth_request = db.exec(
                select(AuthenticationRequest).where(AuthenticationRequest.id == session_record.auth_request_id)
            ).first()

        public_requests = _serialize_requests(db, request_services.list_requests(db), viewer=user)
        pending_requests = _serialize_requests(
            db,
            request_services.list_pending_requests_for_user(db, user_id=user.id),
            viewer=user,
        )

        session_avatar_url = _get_account_avatar(db, user.id)

        context = {
            "request": request,
            "user": user,
            "requests": public_requests,
            "pending_requests": pending_requests,
            "verification_code": auth_request.verification_code if auth_request else None,
            "auth_request": auth_request,
            "readonly": True,
            "session": session_record,
            "session_role": session_role,
            "session_username": user.username,
            "session_avatar_url": session_avatar_url,
        }
        return templates.TemplateResponse("requests/pending.html", context)

    session_avatar_url = _get_account_avatar(db, user.id)

    query_params = request.query_params
    topic_filters = _normalize_filter_values(query_params.getlist("topic"))
    urgency_filters = _normalize_filter_values(query_params.getlist("urgency"))
    status_filters = _normalize_filter_values(query_params.getlist("status"))
    all_query_items = list(query_params.multi_items()) if hasattr(query_params, "multi_items") else list(query_params.items())

    request_objects = request_services.list_requests(db)
    enriched_requests: list[tuple[HelpRequest, set[str], str]] = []
    topic_counts: Counter[str] = Counter()
    urgency_counts: Counter[str] = Counter()
    status_counts: Counter[str] = Counter()

    for help_request in request_objects:
        topics = _infer_request_topics(help_request)
        urgency = _infer_request_urgency(help_request)
        for slug in topics:
            topic_counts[slug] += 1
        urgency_counts[urgency] += 1
        status_counts[help_request.status] += 1
        enriched_requests.append((help_request, topics, urgency))

    filtered_objects = [
        help_request
        for help_request, topics, urgency in enriched_requests
        if _matches_request_filters(topics, urgency, help_request.status, topic_filters, urgency_filters, status_filters)
    ]

    public_requests = _serialize_requests(db, filtered_objects, viewer=user)

    filter_options = {
        "topics": [],
        "urgency": [],
        "status": [],
    }
    base_path = request.url.path
    for topic in FILTER_TOPICS:
        slug = topic["slug"]
        active = slug in topic_filters
        url = _build_filter_url(base_path, all_query_items, "topic", slug, active)
        filter_options["topics"].append(
            {
                "slug": slug,
                "label": topic["label"],
                "active": active,
                "count": topic_counts.get(slug, 0),
                "url": url,
            }
        )
    for level in URGENCY_LEVELS:
        slug = level["slug"]
        active = slug in urgency_filters
        url = _build_filter_url(base_path, all_query_items, "urgency", slug, active)
        filter_options["urgency"].append(
            {
                "slug": slug,
                "label": level["label"],
                "active": active,
                "count": urgency_counts.get(slug, 0),
                "url": url,
            }
        )
    for status_option in STATUS_OPTIONS:
        slug = status_option["slug"]
        active = slug in status_filters
        url = _build_filter_url(base_path, all_query_items, "status", slug, active)
        filter_options["status"].append(
            {
                "slug": slug,
                "label": status_option["label"],
                "active": active,
                "count": status_counts.get(slug, 0),
                "url": url,
            }
        )

    reset_url = _build_reset_url(base_path, all_query_items)
    return templates.TemplateResponse(
        "requests/index.html",
        {
            "request": request,
            "user": user,
            "requests": public_requests,
            "readonly": False,
            "session": session_record,
            "session_role": session_role,
            "session_username": user.username,
            "session_avatar_url": session_avatar_url,
            "filter_options": filter_options,
            "active_filters": {
                "topics": sorted(topic_filters),
                "urgency": sorted(urgency_filters),
                "status": sorted(status_filters),
            },
            "filter_reset_url": reset_url,
        },
    )


@router.get("/browse")
def browse_content(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    page: int = Query(1, ge=1),
    q: Optional[str] = Query(None),
    content_type: Optional[str] = Query("all", alias="type"),
    status: Optional[list[str]] = Query(None),
    tag: Optional[list[str]] = Query(None),
) -> Response:
    viewer = session_user.user
    session_record = session_user.session
    session_role = describe_session_role(viewer, session_record)

    search_query = _normalize_search_term(q)
    active_tab = _sanitize_browse_tab(content_type)

    status_filters = {value for value in _normalize_filter_values(status or []) if value in STATUS_LOOKUP}
    tag_filters = {value for value in _normalize_filter_values(tag or []) if value in FILTER_TOPICS_LOOKUP}

    totals = {
        "requests": _count_requests(db, query_text=search_query, status_filters=status_filters, tag_filters=tag_filters),
        "comments": _count_comments(db, query_text=search_query, status_filters=status_filters, tag_filters=tag_filters),
        "profiles": _count_profiles(db, viewer=viewer, query_text=search_query),
    }
    totals["all"] = totals["requests"] + totals["comments"] + totals["profiles"]

    combined_page: Optional[dict[str, object]] = None
    requests_page: Optional[dict[str, object]] = None
    comments_page: Optional[dict[str, object]] = None
    profiles_page: Optional[dict[str, object]] = None

    if active_tab == "requests":
        requests_page = _fetch_request_page(
            db,
            viewer,
            page=page,
            page_size=BROWSE_PAGE_SIZE,
            query_text=search_query,
            status_filters=status_filters,
            tag_filters=tag_filters,
        )
        pagination = _build_pagination_metadata(request, requests_page["page"], requests_page["total_pages"])
    elif active_tab == "comments":
        comments_page = _fetch_comment_page(
            db,
            viewer,
            page=page,
            page_size=BROWSE_PAGE_SIZE,
            query_text=search_query,
            status_filters=status_filters,
            tag_filters=tag_filters,
        )
        pagination = _build_pagination_metadata(request, comments_page["page"], comments_page["total_pages"])
    elif active_tab == "profiles":
        profiles_page = _fetch_profile_page(
            db,
            viewer,
            page=page,
            page_size=BROWSE_PAGE_SIZE,
            query_text=search_query,
        )
        pagination = _build_pagination_metadata(request, profiles_page["page"], profiles_page["total_pages"])
    else:
        combined_page = _fetch_combined_feed(
            db,
            viewer,
            page=page,
            page_size=BROWSE_PAGE_SIZE,
            query_text=search_query,
            status_filters=status_filters,
            tag_filters=tag_filters,
            totals=totals,
        )
        pagination = _build_pagination_metadata(request, combined_page["page"], combined_page["total_pages"])

    status_options = [
        {
            "slug": option["slug"],
            "label": option["label"],
            "active": option["slug"] in status_filters,
        }
        for option in STATUS_OPTIONS
    ]
    tag_options = [
        {
            "slug": topic["slug"],
            "label": topic["label"],
            "active": topic["slug"] in tag_filters,
        }
        for topic in FILTER_TOPICS
    ]

    tabs = _build_browse_tabs(request, totals, active_tab)
    has_filters = bool(search_query or status_filters or tag_filters)

    reset_items: list[tuple[str, str]] = []
    if active_tab != "all":
        reset_items.append(("type", active_tab))
    reset_query = urlencode(reset_items, doseq=True)
    clear_filters_url = f"{request.url.path}?{reset_query}" if reset_items else request.url.path

    context = {
        "request": request,
        "user": viewer,
        "session": session_record,
        "session_role": session_role,
        "session_username": viewer.username,
        "session_avatar_url": session_user.avatar_url,
        "active_tab": active_tab,
        "tabs": tabs,
        "status_options": status_options,
        "tag_options": tag_options,
        "search_query": search_query or "",
        "status_filters": sorted(status_filters),
        "tag_filters": sorted(tag_filters),
        "has_filters": has_filters,
        "combined_page": combined_page,
        "requests_page": requests_page,
        "comments_page": comments_page,
        "profiles_page": profiles_page,
        "pagination": pagination,
        "topic_lookup": FILTER_TOPICS_LOOKUP,
        "filter_reset_url": clear_filters_url,
        "totals": totals,
        "viewer_is_admin": viewer.is_admin,
    }
    return templates.TemplateResponse("browse/index.html", context)


@router.get("/requests/{request_id}")
def request_detail(
    request: Request,
    request_id: int,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    page: int = Query(1, ge=1),
    chat_q: str = Query("", alias="chat_q"),
    chat_topic: list[str] | None = Query(None, alias="chat_topic"),
    chat_participant: list[int] | None = Query(None, alias="chat_participant"),
) -> Response:
    help_request = request_services.get_request_by_id(db, request_id=request_id)
    chat_filters = {
        "query": (chat_q or "").strip(),
        "topics": [value.strip().lower() for value in (chat_topic or []) if value and value.strip()],
        "participants": [pid for pid in (chat_participant or []) if pid],
    }
    context = _build_request_detail_context(
        request,
        db,
        session_user,
        help_request,
        page=page,
        chat_search_filters=chat_filters,
    )
    return templates.TemplateResponse("requests/detail.html", context)


@router.get("/requests/{request_id}/chat-search")
def request_chat_search(
    request_id: int,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    q: str = Query("", max_length=200),
    participant_id: list[int] | None = Query(None, alias="participant"),
    topic: list[str] | None = Query(None),
    limit: int = Query(request_chat_search_service.DEFAULT_RESULT_LIMIT, ge=1, le=100),
) -> Response:
    help_request = request_services.get_request_by_id(db, request_id=request_id)
    query = (q or "").strip()
    participant_ids = [pid for pid in (participant_id or []) if pid]
    topic_filters = [value.strip().lower() for value in (topic or []) if value and value.strip()]

    index, matches = request_chat_search_service.search_chat(
        db,
        help_request.id,
        query=query,
        participant_ids=participant_ids,
        topics=topic_filters,
        limit=limit,
    )
    attr_key = _signal_display_attr_key(help_request)
    display_names = _load_signal_display_names_for_user_ids(
        db,
        {result.user_id for result in matches},
        attr_key,
    )

    payload = {
        "request_id": help_request.id,
        "query": query,
        "results": [
            {
                **request_chat_search_service.serialize_result(result),
                "display_name": display_names.get(result.user_id),
                "comment_anchor": result.anchor,
            }
            for result in matches
        ],
        "meta": {
            "generated_at": index.generated_at,
            "total_entries": index.entry_count,
            "participants": index.participants,
            "limit": limit,
        },
        "display_names": {str(user_id): name for user_id, name in display_names.items()},
    }
    return JSONResponse(payload)


@router.get("/comments/{comment_id}")
def comment_detail(
    request: Request,
    comment_id: int,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    viewer = session_user.user
    session_record = session_user.session
    session_role = describe_session_role(viewer, session_record)

    comment = db.get(RequestComment, comment_id)
    if not comment or comment.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    help_request = db.get(HelpRequest, comment.help_request_id)
    if not help_request:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    if help_request.status == "pending" and not (
        viewer.is_admin or help_request.created_by_user_id == viewer.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    author = db.get(User, comment.user_id)
    if not author:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    attr_key = _signal_display_attr_key(help_request)
    display_name_map = _load_signal_display_names_for_user_ids(db, {author.id}, attr_key)
    display_name = display_name_map.get(author.id)

    serialized_comment = request_comment_service.serialize_comment(
        comment,
        author,
        display_name=display_name,
    )

    serialized_request = _serialize_requests(db, [help_request], viewer=viewer)
    request_payload = serialized_request[0] if serialized_request else None

    context = {
        "request": request,
        "user": viewer,
        "session": session_record,
        "session_role": session_role,
        "session_username": viewer.username,
        "session_avatar_url": session_user.avatar_url,
        "comment": serialized_comment,
        "comment_author": author,
        "comment_display_name": display_name,
        "request_summary": request_payload,
    }
    return templates.TemplateResponse("comments/detail.html", context)


@router.post("/requests/{request_id}/comments")
async def create_request_comment(
    request: Request,
    request_id: int,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    body: Annotated[Optional[str], Form()] = None,
) -> Response:
    help_request = request_services.get_request_by_id(db, request_id=request_id)
    viewer = session_user.user
    session_record = session_user.session

    if not session_record.is_fully_authenticated:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Fully authenticated session required")

    trimmed_body = (body or "").strip()
    errors: list[str] = []

    try:
        comment = request_comment_service.add_comment(
            db,
            help_request_id=help_request.id,
            user_id=viewer.id,
            body=trimmed_body,
        )
    except ValueError as exc:
        errors.append(str(exc))
        comment = None

    wants_json = _wants_json(request)

    if errors:
        if wants_json:
            return JSONResponse({"errors": errors}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)
        context = _build_request_detail_context(
            request,
            db,
            session_user,
            help_request,
            comment_form_errors=errors,
            comment_form_body=trimmed_body,
        )
        return templates.TemplateResponse(
            "requests/detail.html",
            context,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    db.commit()
    db.refresh(comment)

    try:
        request_chat_search_service.refresh_chat_index(db, help_request.id)
    except Exception:  # pragma: no cover - best-effort cache update
        logger.warning("Failed to refresh chat search index for request %s", help_request.id, exc_info=True)

    comment_payload = request_comment_service.serialize_comment(comment, viewer)
    fragment = templates.get_template("requests/partials/comment.html").render(
        {
            "request": request,
            "comment": comment_payload,
            "can_moderate_comments": viewer.is_admin,
            "can_toggle_sync_scope": viewer.is_admin,
            "request_id": help_request.id,
        }
    )

    if wants_json:
        return JSONResponse({"html": fragment, "comment": comment_payload})

    return RedirectResponse(url=f"/requests/{request_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/requests/{request_id}/comments/{comment_id}/delete")
def delete_request_comment(
    request: Request,
    request_id: int,
    comment_id: int,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    help_request = request_services.get_request_by_id(db, request_id=request_id)
    viewer = session_user.user

    if not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    comment = db.get(RequestComment, comment_id)
    if not comment or comment.help_request_id != help_request.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    request_comment_service.soft_delete_comment(db, comment_id)
    db.commit()

    if _wants_json(request):
        return JSONResponse({"deleted": True, "comment_id": comment_id})

    return RedirectResponse(url=f"/requests/{request_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/invite/new")
def invite_new(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    context = {
        "request": request,
        "inviter_username": session_user.user.username,
        "session": session_user.session,
        "session_role": describe_session_role(session_user.user, session_user.session),
        "session_username": session_user.user.username,
        "session_avatar_url": session_user.avatar_url,
    }
    return templates.TemplateResponse("invite/new.html", context)


CONTACT_EMAIL_MAX_LENGTH = 255
PROFILE_PHOTO_MAX_BYTES = 5 * 1024 * 1024
PROFILE_PHOTO_DIR = Path("static/uploads/profile_photos")
PROFILE_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
PROFILE_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

PROFILE_PHOTO_DIR.mkdir(parents=True, exist_ok=True)


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept:
        return True
    requested_with = request.headers.get("x-requested-with", "")
    return requested_with.lower() in {"fetch", "xmlhttprequest"}



def _build_account_settings_context(
    request: Request,
    db: Session,
    session_user: SessionUser,
    *,
    form_values: Optional[dict[str, Optional[str]]] = None,
    form_message: Optional[str] = None,
    form_status: Optional[str] = None,
    form_errors: Optional[list[str]] = None,
) -> dict[str, object]:
    user = session_user.user
    session_record = session_user.session
    session_avatar_url = _get_account_avatar(db, user.id)
    session_role = describe_session_role(user, session_record)

    if form_values is None:
        form_values = {
            "contact_email": user.contact_email or "",
        }

    return {
        "request": request,
        "user": user,
        "session": session_record,
        "session_role": session_role,
        "session_username": user.username,
        "session_avatar_url": session_avatar_url,
        "form_values": form_values,
        "form_message": form_message,
        "form_status": form_status,
        "form_errors": form_errors or [],
        "current_avatar_url": session_avatar_url,
    }


def _build_request_detail_context(
    request: Request,
    db: Session,
    session_user: SessionUser,
    help_request: HelpRequest,
    *,
    comment_form_errors: Optional[list[str]] = None,
    comment_form_body: str = "",
    page: int = 1,
    chat_search_filters: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    viewer = session_user.user
    session_record = session_user.session

    if help_request.status == "pending" and not (
        viewer.is_admin or help_request.created_by_user_id == viewer.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found")

    creator_usernames = request_services.load_creator_usernames(db, [help_request])
    serialized = RequestResponse.from_model(
        help_request,
        created_by_username=creator_usernames.get(help_request.created_by_user_id),
        can_complete=calculate_can_complete(help_request, viewer),
    )

    readonly = not session_record.is_fully_authenticated
    session_role = describe_session_role(viewer, session_record)

    # Pagination
    comments_per_page = request_comment_service.DEFAULT_COMMENTS_PER_PAGE
    offset = (page - 1) * comments_per_page
    comment_rows, total_comments = request_comment_service.list_comments(
        db, help_request_id=help_request.id, limit=comments_per_page, offset=offset
    )
    attr_key = _signal_display_attr_key(help_request)
    display_names = _load_signal_display_names(db, comment_rows, attr_key)
    comments = [
        request_comment_service.serialize_comment(
            comment,
            author,
            display_name=display_names.get(author.id),
        )
        for comment, author in comment_rows
    ]
    comment_promotions = comment_request_promotion_service.get_promotions_for_comment_ids(
        db, [item["id"] for item in comments]
    )
    settings = config.get_settings()
    show_comment_insights = settings.comment_insights_indicator_enabled and viewer.is_admin
    comment_insights_map: dict[int, dict[str, object]] = {}
    promoted_comment_context: Optional[dict[str, object]] = None
    promotion = db.exec(
        select(CommentPromotion).where(CommentPromotion.request_id == help_request.id)
    ).first()
    if promotion:
        source_comment = db.get(RequestComment, promotion.comment_id)
        if source_comment:
            source_author = db.get(User, source_comment.user_id)
            if source_author:
                insight = comment_llm_insights_service.get_analysis_by_comment_id(source_comment.id)
                display_name_map = _load_signal_display_names_for_user_ids(
                    db,
                    {source_author.id},
                    attr_key,
                )
                promoted_comment_context = {
                    "comment": request_comment_service.serialize_comment(
                        source_comment,
                        source_author,
                        display_name=display_name_map.get(source_author.id),
                    ),
                    "insight": insight,
                    "promotion": promotion,
                }

    if show_comment_insights:
        for item in comments:
            analysis = comment_llm_insights_service.get_analysis_by_comment_id(item["id"])
            if analysis:
                page = request_comment_service.get_comment_page(
                    db,
                    help_request_id=analysis.help_request_id,
                    comment_id=analysis.comment_id,
                )
                comment_insights_map[item["id"]] = {
                    "summary": analysis.summary,
                    "resource_tags": analysis.resource_tags,
                    "request_tags": analysis.request_tags,
                    "audience": analysis.audience,
                    "residency_stage": analysis.residency_stage,
                    "location": analysis.location,
                    "location_precision": analysis.location_precision,
                    "urgency": analysis.urgency,
                    "sentiment": analysis.sentiment,
                    "tags": analysis.tags,
                    "notes": analysis.notes,
                    "run_id": analysis.run_id,
                    "recorded_at": analysis.recorded_at,
                    "page": page,
                }
    can_moderate = viewer.is_admin
    can_toggle_sync_scope = viewer.is_admin

    # Calculate pagination info
    total_pages = max(1, (total_comments + comments_per_page - 1) // comments_per_page) if total_comments else 1
    current_page = min(page, total_pages) if total_pages else 1
    
    def _page_url(target_page: int) -> str:
        url = request.url.include_query_params(page=target_page)
        return str(url)
    
    pagination = {
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_url": _page_url(current_page - 1) if current_page > 1 else None,
        "next_url": _page_url(current_page + 1) if current_page < total_pages else None,
        "current_page": current_page,
        "total_pages": total_pages,
        "total_comments": total_comments,
    }

    show_chat_search_panel = total_comments >= CHAT_SEARCH_MIN_COMMENTS

    chat_filters = chat_search_filters or {}
    chat_query = str(chat_filters.get("query", "") or "").strip()
    participant_filters = [int(pid) for pid in chat_filters.get("participants", []) if pid]
    topic_filters = [str(topic) for topic in chat_filters.get("topics", []) if topic]
    chat_results: list[dict[str, object]] = []
    chat_meta: dict[str, object] | None = None
    related_chats: list[dict[str, object]] = []
    if chat_query or participant_filters or topic_filters:
        index, matches = request_chat_search_service.search_chat(
            db,
            help_request.id,
            query=chat_query,
            participant_ids=participant_filters,
            topics=topic_filters,
        )
        display_names_map = _load_signal_display_names_for_user_ids(
            db,
            {match.user_id for match in matches},
            attr_key,
        )
        chat_results = [
            {
                **request_chat_search_service.serialize_result(match),
                "display_name": display_names_map.get(match.user_id)
                or display_names.get(match.user_id),
            }
            for match in matches
        ]
        chat_meta = {
            "generated_at": index.generated_at,
            "total_entries": index.entry_count,
            "limit": request_chat_search_service.DEFAULT_RESULT_LIMIT,
        }
    else:
        related_chats = request_chat_suggestions.suggest_related_requests(db, help_request.id)

    return {
        "request": request,
        "user": viewer,
        "readonly": readonly,
        "request_item": serialized,
        "session": session_record,
        "session_role": session_role,
        "session_username": viewer.username,
        "session_avatar_url": session_user.avatar_url,
        "comments": comments,
        "can_comment": session_record.is_fully_authenticated,
        "can_promote_comments": session_record.is_fully_authenticated,
        "can_moderate_comments": can_moderate,
        "can_toggle_sync_scope": can_toggle_sync_scope,
        "comment_form_errors": comment_form_errors or [],
        "comment_form_body": comment_form_body,
        "comment_max_length": request_comment_service.MAX_COMMENT_LENGTH,
        "request_id": help_request.id,
        "comment_display_names": display_names,
        "comment_promotions": comment_promotions,
        "pagination": pagination,
        "show_chat_search_panel": show_chat_search_panel,
        "chat_search": {
            "query": chat_query,
            "participants": participant_filters,
            "topics": topic_filters,
            "results": chat_results,
            "meta": chat_meta,
            "has_query": bool(chat_query or participant_filters or topic_filters),
        },
        "related_chat_suggestions": related_chats,
        "comment_insights_enabled": show_comment_insights,
        "comment_insights_map": comment_insights_map,
        "promoted_comment_context": promoted_comment_context,
    }


_SLUG_PATTERN = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    return _SLUG_PATTERN.sub("-", value.strip().lower()).strip("-")


def _signal_display_attr_key(help_request: HelpRequest) -> Optional[str]:
    title = (help_request.title or "").strip()
    if not title.startswith("[Signal]"):
        return None
    _, _, group_name = title.partition("]")
    group_name = group_name.strip()
    if not group_name:
        return None
    slug = _slugify(group_name)
    if not slug:
        return None
    return f"signal_display_name:{slug}"


def _load_signal_display_names(
    db: Session,
    comment_rows: list[tuple[RequestComment, User]],
    attr_key: Optional[str],
) -> dict[int, str]:
    user_ids = {author.id for _, author in comment_rows}
    return _load_signal_display_names_for_user_ids(db, user_ids, attr_key)


def _load_signal_display_names_for_user_ids(
    db: Session,
    user_ids: set[int],
    attr_key: Optional[str],
) -> dict[int, str]:
    if not attr_key or not user_ids:
        return {}
    rows = db.exec(
        select(UserAttribute.user_id, UserAttribute.value)
        .where(UserAttribute.user_id.in_(user_ids))
        .where(UserAttribute.key == attr_key)
    ).all()
    return {user_id: value for user_id, value in rows if value}


def _validate_contact_email(value: str) -> Optional[str]:
    if not value:
        return None
    if len(value) > CONTACT_EMAIL_MAX_LENGTH:
        return "Contact email must be 255 characters or fewer."
    if "@" not in value or value.count("@") != 1:
        return "Enter a valid email address."
    local_part, domain_part = value.split("@", 1)
    if not local_part or not domain_part or "." not in domain_part:
        return "Enter a valid email address."
    return None


async def _store_profile_photo(upload: UploadFile) -> str:
    if not upload or not upload.filename:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select a photo to upload.")

    contents = await upload.read()
    if not contents:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Uploaded photo is empty.")
    if len(contents) > PROFILE_PHOTO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Photo must be 5 MB or smaller.",
        )

    content_type = upload.content_type or ""
    if content_type not in PROFILE_ALLOWED_MIME:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Use JPEG, PNG, or WebP images.")

    suffix = Path(upload.filename).suffix.lower()
    if suffix not in PROFILE_ALLOWED_EXTENSIONS:
        suffix = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }.get(content_type, ".png")

    filename = f"{uuid4().hex}{suffix}"
    destination = PROFILE_PHOTO_DIR / filename
    destination.write_bytes(contents)
    return f"/static/uploads/profile_photos/{filename}"


@router.get("/settings/account")
def account_settings(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    context = _build_account_settings_context(request, db, session_user)
    return templates.TemplateResponse("settings/account.html", context)


@router.post("/settings/account")
async def account_settings_submit(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    contact_email: Annotated[Optional[str], Form()] = None,
    profile_photo: Annotated[Optional[UploadFile], File()] = None,
    remove_photo: Annotated[Optional[str], Form()] = None,
) -> Response:
    normalized_email = (contact_email or "").strip()
    form_values = {"contact_email": normalized_email}
    errors: list[str] = []

    validation_error = _validate_contact_email(normalized_email)
    if validation_error:
        errors.append(validation_error)

    new_avatar_url: Optional[str] = None
    remove_photo_requested = bool(remove_photo)

    if profile_photo and profile_photo.filename:
        try:
            new_avatar_url = await _store_profile_photo(profile_photo)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "Unable to upload photo."
            errors.append(detail)

    if errors:
        context = _build_account_settings_context(
            request,
            db,
            session_user,
            form_values=form_values,
            form_errors=errors,
            form_status="error",
        )
        return templates.TemplateResponse("settings/account.html", context)

    user = session_user.user
    user.contact_email = normalized_email or None
    db.add(user)

    if remove_photo_requested:
        user_attribute_service.delete_attribute(
            db,
            user_id=user.id,
            key=user_attribute_service.PROFILE_PHOTO_URL_KEY,
        )
    elif new_avatar_url:
        user_attribute_service.set_attribute(
            db,
            user_id=user.id,
            key=user_attribute_service.PROFILE_PHOTO_URL_KEY,
            value=new_avatar_url,
            actor_user_id=user.id,
        )

    db.commit()
    db.refresh(user)

    context = _build_account_settings_context(
        request,
        db,
        session_user,
        form_values={"contact_email": user.contact_email or ""},
        form_message="Account details updated.",
        form_status="success",
    )
    return templates.TemplateResponse("settings/account.html", context)


@router.get("/invite/map")
def invite_map(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    user = session_user.user
    invite_map = invite_map_cache_service.get_cached_map(db, user_id=user.id)
    cache_hit = invite_map is not None
    if not invite_map:
        invite_map = invite_graph_service.build_bidirectional_invite_map(
            db,
            root_user_id=user.id,
            max_degree=invite_graph_service.DEFAULT_MAP_DEGREE,
        )
        if invite_map:
            invite_map_cache_service.store_cached_map(db, user_id=user.id, invite_map=invite_map)

    context = {
        "request": request,
        "session": session_user.session,
        "session_role": describe_session_role(user, session_user.session),
        "session_username": user.username,
        "user": user,
        "invite_map": invite_map,
        "invite_map_cache_hit": cache_hit,
    }
    return templates.TemplateResponse("invite/map.html", context)


@router.get("/profile")
def profile(
    request: Request,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    user = session_user.user
    session_record = session_user.session
    is_half_authenticated = not session_record.is_fully_authenticated
    session_role = describe_session_role(user, session_record)

    privilege_descriptors = [
        {
            "key": "member",
            "label": "Standard member",
            "active": True,
            "description": "Can browse community requests and submit new ones once their session is fully verified.",
        },
        {
            "key": "admin",
            "label": "Administrator",
            "active": user.is_admin,
            "description": (
                "Can approve access, manage invites, and moderate requests."
                if user.is_admin
                else "Reserved for administrators who can approve access, manage invites, and moderate requests."
            ),
        },
        {
            "key": "half_auth",
            "label": "Half-authenticated session",
            "active": is_half_authenticated,
            "description": (
                "Verify your login to unlock full access to posting and moderation tools."
                if is_half_authenticated
                else "This session is fully verified; no additional login steps are required."
            ),
        },
    ]

    session_avatar_url = session_user.avatar_url
    active_privileges = [descriptor for descriptor in privilege_descriptors if descriptor["active"]]

    context = {
        "request": request,
        "user": user,
        "session": session_record,
        "session_role": session_role,
        "session_username": user.username,
        "identity": {
            "username": user.username,
            "contact_email": user.contact_email,
            "created_at": user.created_at,
            "avatar_url": session_avatar_url,
        },
        "privileges": active_privileges,
        "is_admin": user.is_admin,
        "is_half_authenticated": is_half_authenticated,
        "session_avatar_url": session_avatar_url,
    }
    return templates.TemplateResponse("profile/index.html", context)


@router.get("/people/{username}")
def profile_view(
    username: str,
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    normalized = auth_service.normalize_username(username)
    person = db.exec(select(User).where(User.username == normalized)).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    viewer = session_user.user
    is_self = viewer.id == person.id
    can_view_contact = viewer.is_admin or is_self
    viewer_session = session_user.session
    viewer_session_role = describe_session_role(viewer, viewer_session)

    avatar_url = user_attribute_service.get_attribute(
        db,
        user_id=person.id,
        key=user_attribute_service.PROFILE_PHOTO_URL_KEY,
    )

    identity = {
        "username": person.username,
        "contact_email": person.contact_email if can_view_contact else None,
        "created_at": person.created_at,
        "avatar_url": avatar_url,
    }

    recent_comments: list[dict[str, object]] = []
    show_recent_comments = viewer.is_admin
    if show_recent_comments:
        rows = request_comment_service.list_recent_comments_for_user(db, person.id)
        for comment, help_request in rows:
            created_at_iso = comment.created_at.isoformat() if comment.created_at else None
            recent_comments.append(
                {
                    "id": comment.id,
                    "body": comment.body,
                    "created_at": comment.created_at,
                    "created_at_iso": created_at_iso,
                    "request_id": help_request.id,
                    "request_title": help_request.title or f"Request #{help_request.id}",
                    "request_url": f"/requests/{help_request.id}",
                    "scope": (comment.sync_scope or "private").title(),
                }
            )

    settings = config.get_settings()
    highlight = None
    highlight_receipts: list[dict[str, object]] = []
    snapshot_links: list[dict[str, object]] = []
    snapshot_request_ctas: list[dict[str, object]] = []
    if settings.profile_signal_glaze_enabled:
        highlight = user_profile_highlight_service.get(db, person.id)
        if highlight:
            highlight_receipts = _format_proof_receipts(highlight.proof_points)
        snapshot = signal_profile_snapshot_service.build_snapshot(
            db,
            person.id,
            group_slug=highlight.source_group if highlight and highlight.source_group else None,
        )
        if snapshot:
            snapshot_links = _format_snapshot_links(snapshot.top_links)
            snapshot_request_ctas = _build_request_ctas(snapshot.request_ids, person.id)

    context = {
        "request": request,
        "viewer": viewer,
        "person": person,
        "identity": identity,
        "is_self": is_self,
        "can_view_contact": can_view_contact,
        "contact_restricted": bool(person.contact_email and not can_view_contact),
        "user": viewer,
        "session": viewer_session,
        "session_role": viewer_session_role,
        "session_username": viewer.username,
        "session_avatar_url": session_user.avatar_url,
        "show_recent_comments": show_recent_comments,
        "recent_comments": recent_comments,
        "recent_comments_limit": request_comment_service.RECENT_PROFILE_COMMENTS_LIMIT,
        "recent_comments_url": f"/people/{person.username}/comments",
        "profile_glaze_enabled": settings.profile_signal_glaze_enabled,
        "profile_highlight": highlight,
        "profile_highlight_receipts": highlight_receipts,
        "profile_snapshot_links": snapshot_links,
        "profile_request_ctas": snapshot_request_ctas,
    }
    return templates.TemplateResponse("profile/show.html", context)


@router.post("/api/metrics")
async def ingest_metric(
    request: Request,
    session_user: SessionUser = Depends(require_session_user),
):
    try:
        payload = await request.json()
    except Exception:  # pragma: no cover - malformed bodies
        raise HTTPException(status_code=400, detail="Invalid payload")

    category = str(payload.get("category", "")).strip().lower()
    event = str(payload.get("event", "")).strip().lower()
    if not category or not event:
        raise HTTPException(status_code=400, detail="category and event required")

    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    sanitized_metadata = {str(key): str(value) for key, value in metadata.items()}
    subject_id = payload.get("subject_id")
    logger.info(
        "metric_event",
        extra={
            "category": category,
            "event": event,
            "viewer_id": session_user.user.id,
            "subject_id": subject_id,
            "metadata": sanitized_metadata,
        },
    )
    return JSONResponse({"ok": True})


@router.get("/people/{username}/comments")
def profile_comments(
    username: str,
    request: Request,
    db: SessionDep,
    page: int = Query(1, ge=1),
    session_user: SessionUser = Depends(require_session_user),
) -> Response:
    viewer = session_user.user
    if not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    normalized = auth_service.normalize_username(username)
    person = db.exec(select(User).where(User.username == normalized)).first()
    if not person:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    rows, total_count = request_comment_service.paginate_comments_for_user(
        db,
        person.id,
        page=page,
    )
    comment_groups: list[dict[str, object]] = []
    for comment, help_request in rows:
        created_at_iso = comment.created_at.isoformat() if comment.created_at else None
        title = help_request.title or f"Request #{help_request.id}"
        group_url = f"/requests/{help_request.id}"
        if not comment_groups or comment_groups[-1]["request_id"] != help_request.id:
            comment_groups.append(
                {
                    "request_id": help_request.id,
                    "request_title": title,
                    "request_url": group_url,
                    "comments": [],
                }
            )
        comment_groups[-1]["comments"].append(
            {
                "id": comment.id,
                "body": comment.body,
                "created_at": comment.created_at,
                "created_at_iso": created_at_iso,
                "scope": (comment.sync_scope or "private").title(),
                "comment_url": f"/comments/{comment.id}",
                "username": person.username,
                "display_name": person.username,
            }
        )

    per_page = request_comment_service.PROFILE_COMMENTS_PER_PAGE
    total_pages = max(1, (total_count + per_page - 1) // per_page) if per_page else 1
    current_page = min(page, total_pages)

    def _page_url(target_page: int) -> str:
        return str(request.url.include_query_params(page=target_page))

    pagination = {
        "has_prev": current_page > 1,
        "has_next": current_page < total_pages,
        "prev_url": _page_url(current_page - 1) if current_page > 1 else None,
        "next_url": _page_url(current_page + 1) if current_page < total_pages else None,
        "current_page": current_page,
        "total_pages": total_pages,
        "total_comments": total_count,
    }

    viewer_session = session_user.session
    context = {
        "request": request,
        "person": person,
        "comment_groups": comment_groups,
        "pagination": pagination,
        "user": viewer,
        "session": viewer_session,
        "session_role": describe_session_role(viewer, viewer_session),
        "session_username": viewer.username,
        "session_avatar_url": session_user.avatar_url,
        "profile_url": f"/people/{person.username}",
    }
    return templates.TemplateResponse("profile/comments.html", context)


@router.post("/requests")
def create_request(
    request: Request,
    db: SessionDep,
    session_user: SessionUser = Depends(require_session_user),
    *,
    description: Annotated[str, Form()],
    contact_email: Annotated[Optional[str], Form()] = None,
):
    status_value = "open" if session_user.session.is_fully_authenticated else "pending"
    request_services.create_request(
        db,
        user=session_user.user,
        description=description,
        contact_email=contact_email,
        status_value=status_value,
    )
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/requests/{request_id}/complete")
def complete_request(
    request_id: int,
    request: Request,
    db: SessionDep,
    user: User = Depends(require_authenticated_user),
):
    request_services.mark_completed(db, request_id=request_id, user=user)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


def _build_request_browse_conditions(
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> list:
    conditions = [HelpRequest.status != "pending"]
    if query_text:
        pattern = f"%{query_text}%"
        conditions.append(
            or_(
                HelpRequest.description.ilike(pattern),
                HelpRequest.title.ilike(pattern),
            )
        )
    if status_filters:
        conditions.append(HelpRequest.status.in_(list(status_filters)))
    topic_clause = _topic_keyword_clause([HelpRequest.description], tag_filters)
    if topic_clause is not None:
        conditions.append(topic_clause)
    return conditions


def _build_comment_browse_conditions(
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> list:
    conditions = [
        RequestComment.deleted_at.is_(None),
        HelpRequest.status != "pending",
    ]
    if query_text:
        pattern = f"%{query_text}%"
        conditions.append(
            or_(
                RequestComment.body.ilike(pattern),
                HelpRequest.description.ilike(pattern),
                HelpRequest.title.ilike(pattern),
            )
        )
    if status_filters:
        conditions.append(HelpRequest.status.in_(list(status_filters)))
    topic_clause = _topic_keyword_clause([RequestComment.body, HelpRequest.description], tag_filters)
    if topic_clause is not None:
        conditions.append(topic_clause)
    return conditions


def _build_profile_browse_conditions(
    db: Session,
    viewer: User,
    query_text: Optional[str],
) -> list:
    conditions: list = []
    visibility_clause = _profile_visibility_clause(db, viewer)
    if visibility_clause is not None:
        conditions.append(visibility_clause)
    if query_text:
        pattern = f"%{query_text}%"
        conditions.append(
            or_(
                User.username.ilike(pattern),
                User.contact_email.ilike(pattern),
            )
        )
    return conditions


def _count_requests(
    db: Session,
    *,
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> int:
    conditions = _build_request_browse_conditions(query_text, status_filters, tag_filters)
    stmt = select(func.count()).select_from(HelpRequest).where(*conditions)
    return int(db.exec(stmt).one() or 0)


def _count_comments(
    db: Session,
    *,
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> int:
    conditions = _build_comment_browse_conditions(query_text, status_filters, tag_filters)
    stmt = (
        select(func.count())
        .select_from(RequestComment)
        .join(HelpRequest, HelpRequest.id == RequestComment.help_request_id)
        .where(*conditions)
    )
    return int(db.exec(stmt).one() or 0)


def _count_profiles(
    db: Session,
    *,
    viewer: User,
    query_text: Optional[str],
) -> int:
    conditions = _build_profile_browse_conditions(db, viewer, query_text)
    stmt = select(func.count()).select_from(User).where(*conditions)
    return int(db.exec(stmt).one() or 0)


def _fetch_request_page(
    db: Session,
    viewer: User,
    *,
    page: int,
    page_size: int,
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> dict[str, object]:
    total = _count_requests(db, query_text=query_text, status_filters=status_filters, tag_filters=tag_filters)
    if not total:
        return {"items": [], "page": 1, "total_pages": 1, "total": 0, "topics": {}}

    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * page_size
    stmt = (
        select(HelpRequest)
        .where(*_build_request_browse_conditions(query_text, status_filters, tag_filters))
        .order_by(HelpRequest.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = db.exec(stmt).all()
    serialized = _serialize_requests(db, rows, viewer=viewer)
    topics_map = {row.id: sorted(_infer_request_topics(row)) for row in rows}
    return {
        "items": serialized,
        "page": current_page,
        "total_pages": total_pages,
        "total": total,
        "topics": topics_map,
    }


def _fetch_comment_page(
    db: Session,
    viewer: User,
    *,
    page: int,
    page_size: int,
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
) -> dict[str, object]:
    total = _count_comments(db, query_text=query_text, status_filters=status_filters, tag_filters=tag_filters)
    if not total:
        return {"items": [], "page": 1, "total_pages": 1, "total": 0}

    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * page_size
    stmt = (
        select(RequestComment, User, HelpRequest)
        .join(User, User.id == RequestComment.user_id)
        .join(HelpRequest, HelpRequest.id == RequestComment.help_request_id)
        .where(*_build_comment_browse_conditions(query_text, status_filters, tag_filters))
        .order_by(RequestComment.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = db.exec(stmt).all()
    entries = []
    for comment, author, help_request in rows:
        payload = request_comment_service.serialize_comment(comment, author)
        entries.append(
            {
                "comment": payload,
                "request": {
                    "id": help_request.id,
                    "title": help_request.title or "Untitled request",
                    "status": help_request.status,
                },
            }
        )
    return {
        "items": entries,
        "page": current_page,
        "total_pages": total_pages,
        "total": total,
    }


def _fetch_profile_page(
    db: Session,
    viewer: User,
    *,
    page: int,
    page_size: int,
    query_text: Optional[str],
) -> dict[str, object]:
    total = _count_profiles(db, viewer=viewer, query_text=query_text)
    if not total:
        return {
            "items": [],
            "page": 1,
            "total_pages": 1,
            "total": 0,
            "avatars": {},
        }

    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * page_size
    stmt = (
        select(User)
        .where(*_build_profile_browse_conditions(db, viewer, query_text))
        .order_by(User.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    rows = db.exec(stmt).all()
    avatar_urls = user_attribute_service.load_profile_photo_urls(
        db,
        user_ids=[user.id for user in rows if user.id],
    )
    return {
        "items": rows,
        "page": current_page,
        "total_pages": total_pages,
        "total": total,
        "avatars": avatar_urls,
    }


def _load_requests_by_ids(db: Session, viewer: User, request_ids: list[int]) -> dict[int, dict[str, object]]:
    if not request_ids:
        return {}
    stmt = select(HelpRequest).where(HelpRequest.id.in_(request_ids))
    rows = db.exec(stmt).all()
    serialized = _serialize_requests(db, rows, viewer=viewer)
    topics_map = {row.id: sorted(_infer_request_topics(row)) for row in rows}
    return {
        item["id"]: {
            "data": item,
            "topics": topics_map.get(item["id"], []),
        }
        for item in serialized
    }


def _load_comments_by_ids(db: Session, comment_ids: list[int]) -> dict[int, dict[str, object]]:
    if not comment_ids:
        return {}
    stmt = (
        select(RequestComment, User, HelpRequest)
        .join(User, User.id == RequestComment.user_id)
        .join(HelpRequest, HelpRequest.id == RequestComment.help_request_id)
        .where(RequestComment.id.in_(comment_ids))
    )
    rows = db.exec(stmt).all()
    lookup: dict[int, dict[str, object]] = {}
    for comment, author, help_request in rows:
        payload = request_comment_service.serialize_comment(comment, author)
        lookup[comment.id] = {
            "comment": payload,
            "request": {
                "id": help_request.id,
                "title": help_request.title or "Untitled request",
                "status": help_request.status,
            },
        }
    return lookup


def _load_profiles_by_ids(db: Session, viewer: User, profile_ids: list[int]) -> dict[int, dict[str, object]]:
    if not profile_ids:
        return {}
    stmt = select(User).where(User.id.in_(profile_ids))
    rows = db.exec(stmt).all()
    avatar_urls = user_attribute_service.load_profile_photo_urls(
        db,
        user_ids=[user.id for user in rows if user.id],
    )
    return {
        user.id: {
            "user": user,
            "avatar_url": avatar_urls.get(user.id),
        }
        for user in rows
        if user.id is not None
    }


def _fetch_combined_feed(
    db: Session,
    viewer: User,
    *,
    page: int,
    page_size: int,
    query_text: Optional[str],
    status_filters: set[str],
    tag_filters: set[str],
    totals: dict[str, int],
) -> dict[str, object]:
    total = totals.get("all", 0)
    if not total:
        return {"items": [], "page": 1, "total_pages": 1, "total": 0}

    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(max(1, page), total_pages)
    offset = (current_page - 1) * page_size

    request_select = (
        select(
            literal("request").label("kind"),
            HelpRequest.id.label("entity_id"),
            HelpRequest.created_at.label("created_at"),
        )
        .where(*_build_request_browse_conditions(query_text, status_filters, tag_filters))
    )
    comment_select = (
        select(
            literal("comment").label("kind"),
            RequestComment.id.label("entity_id"),
            RequestComment.created_at.label("created_at"),
        )
        .select_from(RequestComment)
        .join(HelpRequest, HelpRequest.id == RequestComment.help_request_id)
        .where(*_build_comment_browse_conditions(query_text, status_filters, tag_filters))
    )
    profile_select = (
        select(
            literal("profile").label("kind"),
            User.id.label("entity_id"),
            User.created_at.label("created_at"),
        )
        .where(*_build_profile_browse_conditions(db, viewer, query_text))
    )

    combined_source = union_all(request_select, comment_select, profile_select).subquery()
    stmt = (
        select(
            combined_source.c.kind,
            combined_source.c.entity_id,
            combined_source.c.created_at,
        )
        .order_by(desc(combined_source.c.created_at))
        .offset(offset)
        .limit(page_size)
    )
    rows = db.exec(stmt).all()

    request_ids = [row.entity_id for row in rows if row.kind == "request"]
    comment_ids = [row.entity_id for row in rows if row.kind == "comment"]
    profile_ids = [row.entity_id for row in rows if row.kind == "profile"]

    request_lookup = _load_requests_by_ids(db, viewer, request_ids)
    comment_lookup = _load_comments_by_ids(db, comment_ids)
    profile_lookup = _load_profiles_by_ids(db, viewer, profile_ids)

    entries: list[dict[str, object]] = []
    for row in rows:
        if row.kind == "request":
            payload = request_lookup.get(row.entity_id)
            if not payload:
                continue
            entries.append(
                {
                    "kind": "request",
                    "data": payload["data"],
                    "created_at": row.created_at,
                    "topics": payload["topics"],
                    "href": f"/requests/{payload['data']['id']}",
                    "snippet": _truncate_text(str(payload["data"].get("description") or "")),
                }
            )
        elif row.kind == "comment":
            payload = comment_lookup.get(row.entity_id)
            if not payload:
                continue
            entries.append(
                {
                    "kind": "comment",
                    "data": payload["comment"],
                    "created_at": row.created_at,
                    "request": payload["request"],
                    "href": f"/comments/{payload['comment']['id']}",
                    "snippet": _truncate_text(str(payload["comment"].get("body") or "")),
                }
            )
        elif row.kind == "profile":
            payload = profile_lookup.get(row.entity_id)
            if not payload:
                continue
            profile_user = payload["user"]
            if viewer.is_admin:
                profile_href = f"/admin/profiles/{profile_user.id}"
            elif profile_user.id == viewer.id:
                profile_href = "/profile"
            else:
                profile_href = f"/people/{profile_user.username}"
            entries.append(
                {
                    "kind": "profile",
                    "user": payload["user"],
                    "avatar_url": payload["avatar_url"],
                    "created_at": row.created_at,
                    "href": profile_href,
                }
            )

    return {
        "items": entries,
        "page": current_page,
        "total_pages": total_pages,
        "total": total,
    }


def _get_account_avatar(db: Session, user_id: int) -> Optional[str]:
    return user_attribute_service.get_attribute(
        db,
        user_id=user_id,
        key=user_attribute_service.PROFILE_PHOTO_URL_KEY,
    )


from . import admin as admin_routes
from . import members as members_routes
from . import menu as menu_routes
from . import sessions as session_routes
from . import sync as sync_routes


router.include_router(session_routes.router)
router.include_router(sync_routes.router)
router.include_router(members_routes.router)
router.include_router(menu_routes.router)
router.include_router(admin_routes.router)
