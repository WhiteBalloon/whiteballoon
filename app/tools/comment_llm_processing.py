from __future__ import annotations

import argparse
import asyncio
import json
import math
import textwrap
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from sqlalchemy.sql import Select
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_engine
from app.models import RequestComment
from app.services import (
    comment_attribute_service,
    comment_llm_insights_db,
    comment_llm_store,
)


MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 25
DEFAULT_BATCH_SIZE = 10
DEFAULT_INSTRUCTIONS_TOKENS = 450
DEFAULT_PER_COMMENT_PREFIX_TOKENS = 24
DEFAULT_RESPONSE_TOKENS_PER_COMMENT = 120
DEFAULT_INPUT_COST_PER_1K = 0.00015  # Rough gpt-4o-mini rate
DEFAULT_OUTPUT_COST_PER_1K = 0.0006
DEFAULT_MODEL = "openai/gpt-5-mini"
RESOURCE_TAGS = ["housing", "amenities", "funding", "logistics", "guides"]
REQUEST_TAGS = [
    "housing-request",
    "roommate-matching",
    "event-collaboration",
    "travel",
    "visa-legal",
    "onboarding",
    "emotional-support",
    "funding-request",
]
COMMUNITY_AUDIENCES = ["residents", "hosts", "adjacent", "network"]
RESIDENCY_STAGES = ["pre-arrival", "on-site", "post-residency", "general"]
LOCATION_PRECISION = ["exact", "neighborhood", "city", "regional", "global", "unknown"]
URGENCY_LEVELS = ["low", "medium", "high", "critical"]
SENTIMENT_SCALE = ["positive", "neutral", "negative", "mixed"]
OUTPUT_DIR = Path("storage/comment_llm_runs")
PROMOTION_KEYWORDS = ["need", "please help", "can someone", "urgent", "request"]


@dataclass(frozen=True)
class SnapshotFilters:
    min_id: int | None = None
    max_id: int | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    help_request_ids: tuple[int, ...] = tuple()
    user_ids: tuple[int, ...] = tuple()
    include_deleted: bool = False
    resume_after_id: int | None = None


@dataclass(frozen=True)
class BatchEstimates:
    batch_index: int
    comment_ids: list[int]
    comment_count: int
    estimated_input_tokens: int
    estimated_output_tokens: int


@dataclass(frozen=True)
class RunSummary:
    snapshot_label: str
    total_comments: int
    total_batches: int
    total_input_tokens: int
    total_output_tokens: int
    estimated_cost_usd: float
    batch_size: int
    filters: SnapshotFilters
    batches: list[BatchEstimates]


@dataclass(frozen=True)
class EstimationConfig:
    instructions_tokens: int
    per_comment_prefix_tokens: int
    response_tokens_per_comment: int
    input_cost_per_1k: float
    output_cost_per_1k: float


@dataclass(frozen=True)
class CommentPayload:
    id: int
    help_request_id: int
    user_id: int
    created_at: datetime
    body: str


@dataclass(frozen=True)
class CommentAnalysis:
    comment_id: int
    help_request_id: int
    summary: str
    resource_tags: list[str]
    request_tags: list[str]
    audience: str
    residency_stage: str
    location: str
    location_precision: str
    urgency: str
    sentiment: str
    tags: list[str]
    notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "comment_id": self.comment_id,
            "help_request_id": self.help_request_id,
            "summary": self.summary,
            "resource_tags": self.resource_tags,
            "request_tags": self.request_tags,
            "audience": self.audience,
            "residency_stage": self.residency_stage,
            "location": self.location,
            "location_precision": self.location_precision,
            "urgency": self.urgency,
            "sentiment": self.sentiment,
            "tags": self.tags,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class BatchLLMResult:
    batch_index: int
    analyses: list[CommentAnalysis]
    raw_response: str


class CommentBatchPlanner:
    def __init__(
        self,
        *,
        session: Session,
        filters: SnapshotFilters,
        batch_size: int,
        max_comments: int | None,
        estimation_config: EstimationConfig,
        snapshot_label: str,
        exclude_comment_ids: Sequence[int] | None = None,
    ) -> None:
        if not MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"Batch size must be between {MIN_BATCH_SIZE} and {MAX_BATCH_SIZE}")
        self.session = session
        self.filters = filters
        self.batch_size = batch_size
        self.max_comments = max_comments
        self.estimation_config = estimation_config
        self.snapshot_label = snapshot_label
        self._cached_rows: list[CommentPayload] | None = None
        self.exclude_comment_ids = {int(comment_id) for comment_id in (exclude_comment_ids or [])}

    def plan(self) -> RunSummary:
        rows = self._comment_rows()
        batches = list(self._chunk(rows))
        estimates = [self._estimate_batch(idx, batch) for idx, batch in enumerate(batches, start=1)]
        total_input = sum(item.estimated_input_tokens for item in estimates)
        total_output = sum(item.estimated_output_tokens for item in estimates)
        cost = self._estimate_cost(total_input, total_output)
        return RunSummary(
            snapshot_label=self.snapshot_label,
            total_comments=len(rows),
            total_batches=len(estimates),
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            estimated_cost_usd=cost,
            batch_size=self.batch_size,
            filters=self.filters,
            batches=estimates,
        )

    def _comment_rows(self) -> list[CommentPayload]:
        if self._cached_rows is not None:
            return self._cached_rows
        rows = list(self._load_comments())
        if self.max_comments is not None:
            rows = rows[: self.max_comments]
        self._cached_rows = rows
        return self._cached_rows

    def _load_comments(self) -> Iterable[CommentPayload]:
        stmt = select(RequestComment)
        stmt = stmt.order_by(RequestComment.created_at.asc(), RequestComment.id.asc())
        stmt = self._apply_filters(stmt)
        excluded = self.exclude_comment_ids
        for comment in self.session.exec(stmt):
            if excluded and comment.id in excluded:
                continue
            yield CommentPayload(
                id=comment.id or 0,
                help_request_id=comment.help_request_id,
                user_id=comment.user_id,
                created_at=comment.created_at,
                body=comment.body or "",
            )

    def _apply_filters(self, stmt: Select) -> Select:
        filters = self.filters
        if filters.min_id:
            stmt = stmt.where(RequestComment.id >= filters.min_id)
        if filters.max_id:
            stmt = stmt.where(RequestComment.id <= filters.max_id)
        if filters.resume_after_id:
            stmt = stmt.where(RequestComment.id > filters.resume_after_id)
        if filters.created_after:
            stmt = stmt.where(RequestComment.created_at >= filters.created_after)
        if filters.created_before:
            stmt = stmt.where(RequestComment.created_at <= filters.created_before)
        if filters.help_request_ids:
            stmt = stmt.where(RequestComment.help_request_id.in_(filters.help_request_ids))
        if filters.user_ids:
            stmt = stmt.where(RequestComment.user_id.in_(filters.user_ids))
        if not filters.include_deleted:
            stmt = stmt.where(RequestComment.deleted_at.is_(None))
        return stmt

    def _chunk(self, comments: Sequence[CommentPayload]) -> Iterable[List[CommentPayload]]:
        if not comments:
            return []
        chunks: list[list[CommentPayload]] = []
        for start in range(0, len(comments), self.batch_size):
            chunks.append(list(comments[start : start + self.batch_size]))
        return chunks

    def iter_batches(self) -> Iterable[list[CommentPayload]]:
        return list(self._chunk(self._comment_rows()))

    def _estimate_batch(self, idx: int, comments: Sequence[CommentPayload]) -> BatchEstimates:
        config = self.estimation_config
        per_comment_tokens = [
            estimate_tokens(comment.body) + config.per_comment_prefix_tokens for comment in comments
        ]
        estimated_input_tokens = config.instructions_tokens + sum(per_comment_tokens)
        estimated_output_tokens = len(comments) * config.response_tokens_per_comment
        return BatchEstimates(
            batch_index=idx,
            comment_ids=[comment.id for comment in comments],
            comment_count=len(comments),
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
        )

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return estimate_cost_amount(input_tokens, output_tokens, self.estimation_config)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - argparse already coerces
        raise argparse.ArgumentTypeError(f"Invalid datetime: {value}") from exc


def estimate_tokens(text: str) -> int:
    cleaned = text.strip()
    if not cleaned:
        return 1
    # Rough heuristic: 1 token per 4 characters with a small buffer.
    approx = math.ceil(len(cleaned) / 4)
    return max(1, approx + 4)


def serialize_filters(filters: SnapshotFilters) -> dict[str, object]:
    return {
        "min_id": filters.min_id,
        "max_id": filters.max_id,
        "resume_after_id": filters.resume_after_id,
        "created_after": filters.created_after.isoformat() if filters.created_after else None,
        "created_before": filters.created_before.isoformat() if filters.created_before else None,
        "help_request_ids": list(filters.help_request_ids),
        "user_ids": list(filters.user_ids),
        "include_deleted": filters.include_deleted,
    }


def estimate_cost_amount(input_tokens: int, output_tokens: int, config: EstimationConfig) -> float:
    input_cost = (input_tokens / 1000) * config.input_cost_per_1k
    output_cost = (output_tokens / 1000) * config.output_cost_per_1k
    return round(input_cost + output_cost, 6)


def _rubric_instructions(batch_index: int) -> str:
    return textwrap.dedent(
        f"""
        You analyze hacker-house community comments and must produce structured JSON.
        Follow this rubric:
        - resource_tags: choose 0-3 of {', '.join(RESOURCE_TAGS)} to describe tangible offers/resources.
        - request_tags: choose 0-3 of {', '.join(REQUEST_TAGS)} for asks/needs.
        - audience: one of {', '.join(COMMUNITY_AUDIENCES)} (residents living there, hosts/staff, adjacent collaborators like sponsors, or the broader network).
        - residency_stage: one of {', '.join(RESIDENCY_STAGES)} describing when the comment matters.
        - location_precision: one of {', '.join(LOCATION_PRECISION)}.
        - urgency: one of {', '.join(URGENCY_LEVELS)}.
        - sentiment: one of {', '.join(SENTIMENT_SCALE)}.
        - tags: optional extra descriptors in kebab-case (e.g., "airport-run", "mentorship").
        Output JSON ONLY with this schema:
        {{
          "batch_index": {batch_index},
          "comments": [
            {{
              "comment_id": <int>,
              "summary": "<=120 char overview",
              "resource_tags": ["housing"],
              "request_tags": ["travel"],
              "audience": "residents",
              "residency_stage": "on-site",
              "location": "Hacker House SF",
              "location_precision": "city",
              "urgency": "medium",
              "sentiment": "mixed",
              "tags": ["airport-run"],
              "notes": "Optional clarifications"
            }}
          ]
        }}
        Never add commentary or markdown fences—return JSON only.
        """
    ).strip()


def _format_comment_block(idx: int, payload: CommentPayload) -> str:
    created = payload.created_at.isoformat()
    body = payload.body.strip()
    return textwrap.dedent(
        f"""
        ### Comment {idx}
        comment_id: {payload.id}
        help_request_id: {payload.help_request_id}
        user_id: {payload.user_id}
        created_at: {created}
        body:\n        \"\"\"{body}\"\"\"
        """
    ).strip()


def build_prompt(batch_index: int, comments: Sequence[CommentPayload]) -> str:
    sections = [_format_comment_block(idx, payload) for idx, payload in enumerate(comments, start=1)]
    return _rubric_instructions(batch_index) + "\n\n" + "\n\n".join(sections)


def _extract_json_blob(raw: str) -> str:
    text = raw.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if part.lower().startswith("json"):
                candidate = part[4:].strip()
            else:
                candidate = part
            if candidate.startswith("{"):
                text = candidate
                break
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Unable to locate JSON payload in model response")
    return text[start : end + 1]


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [chunk.strip() for chunk in text.split(",") if chunk.strip()]
    return []


def parse_batch_response(
    raw_response: str,
    *,
    batch_index: int,
    expected_comments: dict[int, CommentPayload],
) -> BatchLLMResult:
    blob = _extract_json_blob(raw_response)
    payload = json.loads(blob)
    items = payload.get("comments")
    if not isinstance(items, list):
        raise ValueError("Model response missing 'comments' array")
    analyses: list[CommentAnalysis] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if "comment_id" not in item:
            raise ValueError("Model output missing comment_id field")
        comment_id = int(item.get("comment_id"))
        source = expected_comments.get(comment_id)
        if not source:
            raise ValueError(f"Unexpected comment_id {comment_id} in batch {batch_index}")
        analysis = CommentAnalysis(
            comment_id=comment_id,
            help_request_id=source.help_request_id,
            summary=str(item.get("summary", "")).strip(),
            resource_tags=_normalize_list(item.get("resource_tags")),
            request_tags=_normalize_list(item.get("request_tags")),
            audience=str(item.get("audience", "")).strip().lower() or "unknown",
            residency_stage=str(item.get("residency_stage", "")).strip().lower() or "general",
            location=str(item.get("location", "")).strip(),
            location_precision=str(item.get("location_precision", "")).strip().lower() or "unknown",
            urgency=str(item.get("urgency", "")).strip().lower() or "medium",
            sentiment=str(item.get("sentiment", "")).strip().lower() or "neutral",
            tags=_normalize_list(item.get("tags")),
            notes=str(item.get("notes", "")).strip(),
        )
        analyses.append(analysis)
    expected_ids = {comment.id for comment in expected_comments.values()}
    actual_ids = {analysis.comment_id for analysis in analyses}
    if expected_ids != actual_ids:
        missing = expected_ids - actual_ids
        raise ValueError(
            f"Batch {batch_index} missing analyses for comment IDs: {', '.join(map(str, sorted(missing)))}"
        )
    return BatchLLMResult(batch_index=batch_index, analyses=analyses, raw_response=raw_response)


class BatchLLMClient:
    def analyze_batch(self, *, batch_index: int, comments: Sequence[CommentPayload]) -> BatchLLMResult:  # pragma: no cover - protocol
        raise NotImplementedError


class MockBatchLLMClient(BatchLLMClient):
    def analyze_batch(self, *, batch_index: int, comments: Sequence[CommentPayload]) -> BatchLLMResult:
        payload = {
            "batch_index": batch_index,
            "comments": [],
        }
        for comment in comments:
            body = comment.body.strip()
            first_line = body.splitlines()[0] if body else ""
            summary = first_line[:120] if first_line else "No content provided"
            resource = "housing" if "room" in body.lower() else "logistics"
            payload["comments"].append(
                {
                    "comment_id": comment.id,
                    "summary": summary,
                    "resource_tags": [resource],
                    "request_tags": ["travel"] if "flight" in body.lower() else [],
                    "audience": "residents",
                    "residency_stage": "on-site",
                    "location": "",
                    "location_precision": "unknown",
                    "urgency": "medium",
                    "sentiment": "neutral",
                    "tags": ["mock"],
                    "notes": "Mock provider generated this entry",
                }
            )
        raw = json.dumps(payload, indent=2)
        expected = {comment.id: comment for comment in comments}
        return parse_batch_response(raw, batch_index=batch_index, expected_comments=expected)


class DedalusBatchLLMClient(BatchLLMClient):
    def __init__(self, *, model: str, max_retries: int, retry_wait: float) -> None:
        try:
            from dedalus_labs import AsyncDedalus, DedalusRunner  # type: ignore
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise RuntimeError("Install the 'dedalus-labs' package to execute batches via the LLM.") from exc

        settings = get_settings()
        api_key = settings.dedalus_api_key
        try:
            if api_key:
                client = AsyncDedalus(api_key=api_key)
            else:
                client = AsyncDedalus()
        except TypeError:  # pragma: no cover - backwards compatibility when api_key optional
            client = AsyncDedalus()

        self._runner = DedalusRunner(client)
        self._model = model or DEFAULT_MODEL
        self._max_retries = max(0, max_retries)
        self._retry_wait = max(0.5, retry_wait)

    async def _run_async(self, prompt: str) -> str:
        response = await self._runner.run(input=prompt, model=self._model)
        final = getattr(response, "final_output", None)
        if final:
            return str(final)
        outputs = getattr(response, "outputs", None)
        if isinstance(outputs, list) and outputs:
            return "\n".join(str(item) for item in outputs)
        return str(response)

    def analyze_batch(self, *, batch_index: int, comments: Sequence[CommentPayload]) -> BatchLLMResult:
        expected = {comment.id: comment for comment in comments}
        prompt = build_prompt(batch_index, comments)
        attempts = 0
        while True:
            try:
                raw = asyncio.run(self._run_async(prompt))
                return parse_batch_response(raw, batch_index=batch_index, expected_comments=expected)
            except Exception as exc:  # pragma: no cover - external dependency
                attempts += 1
                if attempts > self._max_retries:
                    raise
                delay = self._retry_wait * attempts
                print(
                    f"[batch {batch_index:03d}] Dedalus call failed ({exc}); retrying in {delay:.1f}s...")
                time.sleep(delay)


def build_llm_client(
    *, provider: str, model: str, max_retries: int, retry_wait: float
) -> BatchLLMClient:
    if provider == "mock":
        return MockBatchLLMClient()
    return DedalusBatchLLMClient(model=model, max_retries=max_retries, retry_wait=retry_wait)


def _default_output_path(snapshot_label: str, *, started_at: datetime | None = None) -> Path:
    slug = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in snapshot_label.lower())
    slug = slug.strip("-") or "snapshot"
    timestamp = (started_at or datetime.utcnow()).strftime("%Y%m%d-%H%M%S")
    return OUTPUT_DIR / f"{slug}_{timestamp}.json"


def persist_execution_results(
    *,
    summary: RunSummary,
    results: Sequence[BatchLLMResult],
    output_path: Path,
    provider: str,
    model: str,
    run_id: str,
) -> Path:
    estimate_lookup = {batch.batch_index: batch for batch in summary.batches}
    payload = {
        "snapshot_label": summary.snapshot_label,
        "generated_at": datetime.utcnow().isoformat(),
        "provider": provider,
        "model": model,
        "run_id": run_id,
        "batch_size": summary.batch_size,
        "total_planned_comments": summary.total_comments,
        "total_planned_batches": summary.total_batches,
        "estimated_input_tokens": summary.total_input_tokens,
        "estimated_output_tokens": summary.total_output_tokens,
        "estimated_cost_usd": summary.estimated_cost_usd,
        "filters": serialize_filters(summary.filters),
        "batches": [],
    }
    for result in results:
        estimate = estimate_lookup.get(result.batch_index)
        payload["batches"].append(
            {
                "batch_index": result.batch_index,
                "comment_ids": [analysis.comment_id for analysis in result.analyses],
                "estimated_input_tokens": estimate.estimated_input_tokens if estimate else None,
                "estimated_output_tokens": estimate.estimated_output_tokens if estimate else None,
                "raw_response": result.raw_response,
                "analyses": [analysis.to_dict() for analysis in result.analyses],
            }
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2))
    return output_path


def _analysis_is_request_candidate(analysis: CommentAnalysis) -> tuple[bool, str | None, dict[str, object]]:
    metadata = {
        "resource_tags": analysis.resource_tags,
        "request_tags": analysis.request_tags,
        "audience": analysis.audience,
        "residency_stage": analysis.residency_stage,
        "location": analysis.location,
        "location_precision": analysis.location_precision,
        "urgency": analysis.urgency,
        "sentiment": analysis.sentiment,
        "tags": analysis.tags,
        "summary": analysis.summary,
    }
    if analysis.request_tags:
        return True, f"request_tags:{','.join(analysis.request_tags)}", metadata
    summary = (analysis.summary or "").lower()
    for keyword in PROMOTION_KEYWORDS:
        if keyword in summary:
            return True, f"keyword:{keyword}", metadata
    return False, None, metadata


def _queue_promotion_candidates(
    engine,
    results: Sequence[BatchLLMResult],
    run_id: str,
) -> None:
    if not results:
        return
    analyses = [analysis for result in results for analysis in result.analyses]
    if not analyses:
        return
    queued = 0
    with Session(engine) as session:
        for analysis in analyses:
            should_queue, reason, metadata = _analysis_is_request_candidate(analysis)
            if not should_queue or not reason:
                continue
            comment_attribute_service.queue_promotion_candidate(
                session,
                comment_id=analysis.comment_id,
                reason=reason,
                run_id=run_id,
                metadata=metadata,
            )
            queued += 1
    if queued:
        print(f"Queued {queued} request-like comments for promotion.")


def _rows_for_insights_db(analyses: Sequence[CommentAnalysis], run_id: str, recorded_at: str) -> list[tuple]:
    rows: list[tuple] = []
    for analysis in analyses:
        rows.append(
            (
                analysis.comment_id,
                run_id,
                analysis.help_request_id,
                analysis.summary,
                json.dumps(analysis.resource_tags),
                json.dumps(analysis.request_tags),
                analysis.audience,
                analysis.residency_stage,
                analysis.location,
                analysis.location_precision,
                analysis.urgency,
                analysis.sentiment,
                json.dumps(analysis.tags),
                analysis.notes,
                recorded_at,
            )
        )
    return rows


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.tools.comment_llm_processing",
        description=(
            "Plan batched LLM processing for help-request comments.\n\n"
            "Example:\n  wb comment-llm --snapshot-label hacker-houses-apr --limit 200 --batch-size 10 "
            "--execute --provider dedalus --max-spend-usd 5 --show-batches"
        ),
    )
    parser.add_argument("--snapshot-label", default="default", help="Label recorded with this run plan")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Comments per batch (1-25)")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of comments to include")
    parser.add_argument("--min-id", type=int, help="Minimum comment ID (inclusive)")
    parser.add_argument("--max-id", type=int, help="Maximum comment ID (inclusive)")
    parser.add_argument("--resume-after-id", type=int, help="Skip comments up to and including this ID")
    parser.add_argument("--created-after", type=_parse_datetime, help="Only include comments created at or after this timestamp (ISO8601)")
    parser.add_argument("--created-before", type=_parse_datetime, help="Only include comments created at or before this timestamp (ISO8601)")
    parser.add_argument(
        "--help-request-id",
        action="append",
        type=int,
        dest="help_request_ids",
        help="Restrict processing to specific help request IDs (repeatable)",
    )
    parser.add_argument(
        "--user-id",
        action="append",
        type=int,
        dest="user_ids",
        help="Restrict processing to specific commenter user IDs (repeatable)",
    )
    parser.add_argument("--include-deleted", action="store_true", help="Include comments marked as deleted")
    parser.add_argument(
        "--include-processed",
        action="store_true",
        help="Process comments even if analyses already exist for them",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Send each batch to the LLM after planning (default: plan only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force plan-only mode even if --execute is provided",
    )
    parser.add_argument("--json-summary", action="store_true", help="Emit the plan as JSON instead of text")
    parser.add_argument("--show-batches", action="store_true", help="Print a per-batch breakdown")
    parser.add_argument(
        "--instructions-tokens",
        type=int,
        default=DEFAULT_INSTRUCTIONS_TOKENS,
        help="Estimated tokens for shared instructions per batch",
    )
    parser.add_argument(
        "--per-comment-prefix-tokens",
        type=int,
        default=DEFAULT_PER_COMMENT_PREFIX_TOKENS,
        help="Estimated tokens for per-comment framing/metadata",
    )
    parser.add_argument(
        "--response-tokens-per-comment",
        type=int,
        default=DEFAULT_RESPONSE_TOKENS_PER_COMMENT,
        help="Estimated tokens returned per comment",
    )
    parser.add_argument(
        "--input-cost-per-1k",
        type=float,
        default=DEFAULT_INPUT_COST_PER_1K,
        help="Input token price in USD per 1k tokens",
    )
    parser.add_argument(
        "--output-cost-per-1k",
        type=float,
        default=DEFAULT_OUTPUT_COST_PER_1K,
        help="Output token price in USD per 1k tokens",
    )
    parser.add_argument(
        "--provider",
        choices=("dedalus", "mock"),
        default="dedalus",
        help="LLM backend to use when executing batches (default: %(default)s)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help="LLM model alias (Dedalus provider)")
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="LLM retry attempts per batch (default: %(default)s)",
    )
    parser.add_argument(
        "--retry-wait",
        type=float,
        default=3.0,
        help="Base seconds between retries (scaled by attempt count)",
    )
    parser.add_argument(
        "--output-path",
        help="Where to write structured JSON results when executing batches (default: storage/comment_llm_runs/{snapshot_label}_<timestamp>.json)",
    )
    parser.add_argument(
        "--max-spend-usd",
        type=float,
        default=None,
        help="Ceiling for estimated spend; execution stops before the next batch would exceed it",
    )
    parser.add_argument(
        "--batches-per-minute",
        type=float,
        default=0.0,
        help="Throttle batch submissions to this rate (0 disables throttling)",
    )
    return parser


def _validate_batch_size(value: int) -> None:
    if not MIN_BATCH_SIZE <= value <= MAX_BATCH_SIZE:
        raise ValueError(f"Batch size must be between {MIN_BATCH_SIZE} and {MAX_BATCH_SIZE}")


def human_summary(summary: RunSummary, snapshot_label: str) -> str:
    lines = []
    lines.append(f"Snapshot: {snapshot_label}")
    lines.append(
        f"Totals: {summary.total_comments} comments across {summary.total_batches} batches (size ≤ {summary.batch_size})"
    )
    lines.append(
        f"Tokens: ~{summary.total_input_tokens:,} input / ~{summary.total_output_tokens:,} output"
    )
    lines.append(f"Estimated cost: ${summary.estimated_cost_usd:.4f}")
    filters = summary.filters
    filter_bits = []
    if filters.min_id:
        filter_bits.append(f"min_id={filters.min_id}")
    if filters.max_id:
        filter_bits.append(f"max_id={filters.max_id}")
    if filters.resume_after_id:
        filter_bits.append(f"resume_after_id={filters.resume_after_id}")
    if filters.created_after:
        filter_bits.append(f"created_after={filters.created_after.isoformat()}")
    if filters.created_before:
        filter_bits.append(f"created_before={filters.created_before.isoformat()}")
    if filters.help_request_ids:
        filter_bits.append(f"help_request_ids={','.join(map(str, filters.help_request_ids))}")
    if filters.user_ids:
        filter_bits.append(f"user_ids={','.join(map(str, filters.user_ids))}")
    if not filters.include_deleted:
        filter_bits.append("excluding deleted")
    lines.append("Filters: " + (", ".join(filter_bits) if filter_bits else "(none)"))
    return "\n".join(lines)


def print_batches(batches: Sequence[BatchEstimates]) -> None:
    for batch in batches:
        first = batch.comment_ids[0]
        last = batch.comment_ids[-1]
        print(
            f"Batch {batch.batch_index:03d}: {batch.comment_count} comments (IDs {first}-{last}) -> "
            f"~{batch.estimated_input_tokens} in / ~{batch.estimated_output_tokens} out tokens"
        )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)

    _validate_batch_size(ns.batch_size)

    filters = SnapshotFilters(
        min_id=ns.min_id,
        max_id=ns.max_id,
        created_after=ns.created_after,
        created_before=ns.created_before,
        help_request_ids=tuple(sorted(set(ns.help_request_ids or []))),
        user_ids=tuple(sorted(set(ns.user_ids or []))),
        include_deleted=ns.include_deleted,
        resume_after_id=ns.resume_after_id,
    )
    config = EstimationConfig(
        instructions_tokens=ns.instructions_tokens,
        per_comment_prefix_tokens=ns.per_comment_prefix_tokens,
        response_tokens_per_comment=ns.response_tokens_per_comment,
        input_cost_per_1k=ns.input_cost_per_1k,
        output_cost_per_1k=ns.output_cost_per_1k,
    )

    exclude_ids: set[int] = set()
    if not ns.include_processed:
        exclude_ids = comment_llm_store.recorded_comment_ids()
        if exclude_ids:
            print(
                f"Skipping {len(exclude_ids)} comments with stored analyses (use --include-processed to override)."
            )

    engine = get_engine()
    with Session(engine) as session:
        planner = CommentBatchPlanner(
            session=session,
            filters=filters,
            batch_size=ns.batch_size,
            max_comments=ns.limit,
            estimation_config=config,
            snapshot_label=ns.snapshot_label,
            exclude_comment_ids=exclude_ids,
        )
        summary = planner.plan()

    if ns.json_summary:
        payload = {
            "snapshot_label": summary.snapshot_label,
            "total_comments": summary.total_comments,
            "total_batches": summary.total_batches,
            "batch_size": summary.batch_size,
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
            "estimated_cost_usd": summary.estimated_cost_usd,
            "filters": serialize_filters(summary.filters),
            "batches": [
                {
                    "index": batch.batch_index,
                    "comment_ids": batch.comment_ids,
                    "comment_count": batch.comment_count,
                    "estimated_input_tokens": batch.estimated_input_tokens,
                    "estimated_output_tokens": batch.estimated_output_tokens,
                }
                for batch in summary.batches
            ],
        }
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(human_summary(summary, summary.snapshot_label))
        if ns.show_batches and summary.batches:
            print("\nBatch breakdown:")
            print_batches(summary.batches)

    if summary.total_comments == 0:
        print("No comments matched the supplied filters.")
        return 0

    run_batches = bool(ns.execute and not ns.dry_run)
    if not run_batches:
        if not ns.json_summary:
            print("\nPlan-only mode. Re-run with --execute to process batches via the LLM.")
        return 0

    try:
        client = build_llm_client(
            provider=ns.provider,
            model=ns.model,
            max_retries=ns.max_retries,
            retry_wait=ns.retry_wait,
        )
    except RuntimeError as exc:
        parser.error(str(exc))

    batch_payloads = list(planner.iter_batches())
    if not batch_payloads:
        print("No batches available for execution.")
        return 0

    print("\nExecuting LLM batches...")
    execution_results: list[BatchLLMResult] = []
    run_started_at = datetime.utcnow()
    run_id = f"{summary.snapshot_label}-{run_started_at.strftime('%Y%m%d-%H%M%S')}"
    cumulative_estimated_cost = 0.0
    max_spend = ns.max_spend_usd if ns.max_spend_usd and ns.max_spend_usd > 0 else None
    batches_per_minute = ns.batches_per_minute if ns.batches_per_minute and ns.batches_per_minute > 0 else None
    rate_interval = (60.0 / batches_per_minute) if batches_per_minute else None
    next_allowed_time = time.monotonic() if rate_interval else None
    total_batches = len(batch_payloads)
    with comment_llm_insights_db.open_connection() as db_conn:
        comment_llm_insights_db.insert_run(
            db_conn,
            comment_llm_insights_db.RunRecord(
                run_id=run_id,
                snapshot_label=summary.snapshot_label,
                provider=ns.provider,
                model=ns.model,
                started_at=run_started_at.isoformat(),
                completed_batches=0,
                total_batches=total_batches,
            ),
        )

        try:
            for idx, batch_comments in enumerate(batch_payloads, start=1):
                if rate_interval and next_allowed_time is not None:
                    now = time.monotonic()
                    if now < next_allowed_time:
                        delay = next_allowed_time - now
                        print(
                            f"[batch {idx:03d}] Pausing {delay:.2f}s to honor {batches_per_minute:.1f} batches/min rate."
                        )
                        time.sleep(delay)
                    next_allowed_time = time.monotonic() + rate_interval
                estimate = summary.batches[idx - 1] if idx - 1 < len(summary.batches) else None
                est_input = estimate.estimated_input_tokens if estimate else 0
                est_output = estimate.estimated_output_tokens if estimate else 0
                est_cost = (
                    estimate_cost_amount(est_input, est_output, config) if estimate else 0.0
                )
                projected_cost = cumulative_estimated_cost + est_cost
                if max_spend is not None and projected_cost > max_spend + 1e-9:
                    print(
                        f"[batch {idx:03d}] Stopping before execution: projected spend ${projected_cost:.4f} would exceed max ${max_spend:.4f}."
                    )
                    break
                cumulative_estimated_cost = projected_cost
                print(
                    f"[batch {idx:03d}] Sending {len(batch_comments)} comments "
                    f"(~{est_input} in / ~{est_output} out tokens, est cost ${est_cost:.4f})"
                )
                result = client.analyze_batch(batch_index=idx, comments=batch_comments)
                print(
                    f"[batch {idx:03d}] Received {len(result.analyses)} analyses; cumulative est cost ${cumulative_estimated_cost:.4f}"
                )
                stats = comment_llm_store.save_comment_analyses(
                    analyses=result.analyses,
                    snapshot_label=summary.snapshot_label,
                    provider=ns.provider,
                    model=ns.model,
                    run_id=run_id,
                    batch_index=idx,
                    overwrite=ns.include_processed,
                )
                if stats.written or stats.skipped:
                    print(
                        f"[batch {idx:03d}] Stored {stats.written} analyses ({stats.skipped} skipped)."
                    )
                recorded_at = datetime.utcnow().isoformat()
                rows = _rows_for_insights_db(result.analyses, run_id, recorded_at)
                if rows:
                    comment_llm_insights_db.insert_analyses(db_conn, rows)
                execution_results.append(result)
                comment_llm_insights_db.insert_run(
                    db_conn,
                    comment_llm_insights_db.RunRecord(
                        run_id=run_id,
                        snapshot_label=summary.snapshot_label,
                        provider=ns.provider,
                        model=ns.model,
                        started_at=run_started_at.isoformat(),
                        completed_batches=len(execution_results),
                        total_batches=total_batches,
                    ),
                )
        except KeyboardInterrupt:
            print("\nInterrupted; stopping batch execution early.")
            # fall through to persist whatever results we have

        output_path = (
            Path(ns.output_path)
            if ns.output_path
            else _default_output_path(summary.snapshot_label, started_at=run_started_at)
        )
        saved_path = persist_execution_results(
            summary=summary,
            results=execution_results,
            output_path=output_path,
            provider=ns.provider,
            model=ns.model,
            run_id=run_id,
        )
        print(
            f"\nSaved structured batch output to {saved_path} (processed {len(execution_results)} / {len(batch_payloads)} batches, est spend ${cumulative_estimated_cost:.4f})."
        )
        comment_llm_insights_db.insert_run(
            db_conn,
            comment_llm_insights_db.RunRecord(
                run_id=run_id,
                snapshot_label=summary.snapshot_label,
                provider=ns.provider,
                model=ns.model,
                started_at=run_started_at.isoformat(),
                completed_batches=len(execution_results),
                total_batches=total_batches,
            ),
        )
    _queue_promotion_candidates(engine, execution_results, run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
