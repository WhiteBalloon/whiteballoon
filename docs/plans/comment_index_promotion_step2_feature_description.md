## Problem
The comment indexing script detects request-like comments, but promotions still require manual scripts. We want the indexer to queue promotions automatically using a DB-backed model so a worker can process them without new bespoke tables.

## User Stories
- As an operator, I want request-looking comments to appear as HelpRequests automatically once the indexing job runs.
- As a developer, I want the indexer to record promotion candidates in a structured place (comment attributes) so the promotion worker can resume/retry safely.
- As an admin, I want to see an audit trail (attribute entries) that shows which comments were queued/promoted.

## Core Requirements
- Introduce a `comment_attributes` table (similar to `user_attributes`) supporting arbitrary key/value metadata per `RequestComment` (e.g., key `promotion_queue`, JSON value with reason/run_id/status).
- Extend the indexing script to detect request-like comments and upsert a `promotion_queue` attribute with metadata (score, reason, run_id, status=`pending`).
- Build a promotion worker/CLI that scans `comment_attributes` entries with `promotion_queue` pending, calls `promote_comment_to_request`, and updates the attribute (e.g., status=`completed`, reference request_id) or records errors.
- Ensure idempotency: re-running indexing shouldn’t create duplicate attributes; promotion worker should skip attributes already marked completed unless forced.
- Provide simple introspection (CLI command) to list pending/failed promotion attributes.

## Shared Component Inventory
- `app/models.py` – add `CommentAttribute` SQLModel (mirroring `UserAttribute`).
- `app/services/comment_request_promotion_service.py` – reuse existing promotion logic; possibly add helper to check attributes.
- `app/tools/comment_llm_processing.py` – update to upsert `CommentAttribute` rows while indexing.
- New CLI (`wb promote-comment-batch`, `wb promote-comment-queue`) – consume attributes, promote, and update status.

## Simple User Flow
1. Indexing job runs, and when a comment looks like a request, it upserts a `promotion_queue` attribute with `status=pending` and metadata.
2. Promotion worker/CLI reads pending attributes, promotes via the existing service, and updates the attribute to `status=completed` (with request_id) or `status=failed` with error info.
3. Operators can view pending/failed entries via CLI or admin SQL queries.

## Success Criteria
- Indexing job records promotion candidates using comment attributes without significant overhead.
- Promotion worker processes pending attributes into HelpRequests idempotently, updating status for auditing.
- CLI visibility for pending/failed entries.
- No manual intervention needed beyond monitoring.
