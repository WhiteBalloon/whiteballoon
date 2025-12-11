# Comment Index Promotion – Step 4 Implementation Summary

## Stage 1 – Comment attributes model
- Added `CommentAttribute` SQLModel/table (mirroring `UserAttribute`) with a unique `(comment_id, key)` constraint so we can store arbitrary metadata per comment. Introduced helper functions in `app/services/comment_attribute_service.py` to upsert, list, and update promotion queue entries.
- Verification: Ran `python - <<'PY' ...` inserts during testing to confirm rows persist and the unique constraint holds; reran `wb init-db` to create the new table locally.

## Stage 2 – Indexer integration
- Updated `app/tools/comment_llm_processing.py` to detect request-like comments (using LLM `request_tags` or keyword heuristics) after each batch and queue them via `comment_attribute_service.queue_promotion_candidate`. Each candidate attribute stores `status=pending`, `reason`, and `run_id` metadata.
- Verification: Executed the indexer on sample comments and observed console output (“Queued N request-like comments for promotion”) plus DB attributes populated with pending entries.

## Stage 3 – Promotion worker CLI
- Added `app/tools/comment_promotion_batch.py` (+ `wb promote-comment-batch`) with subcommands:
  - `run` processes pending queue entries by loading the comment + author, calling `promote_comment_to_request(source='indexer')`, and marking attributes `completed` or `failed` (with error + attempt count).
  - `list` shows pending/completed/failed entries for visibility.
  - `retry` resets an attribute back to `pending` for reprocessing.
- Verification: Seeded queue attributes manually, ran `wb promote-comment-batch run --limit 5`, and confirmed new HelpRequests appeared while attributes flipped to `completed` or `failed` with clear messages.

## Stage 4 – Visibility & docs
- Implemented the `list`/`retry` commands described above so operators can inspect/requeue entries without direct SQL. Documented the workflow via CLI help output; future admin UI can build on the same attribute data.
- Verification: Ran `wb promote-comment-batch list --status pending` and `... retry <id>` to ensured output matches DB state.
