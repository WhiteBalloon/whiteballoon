## Stage 1 – Comment attributes model
- **Goal**: Add a `CommentAttribute` SQLModel/table mirroring `UserAttribute` (`comment_id`, `key`, `value`, timestamps, unique constraint per key).
- **Dependencies**: `app/models.py`, DB migration (if needed).
- **Changes**: Define the model, include it in metadata, ensure migrations create the table. Add helper functions (`get_comment_attribute`, `upsert_comment_attribute`).
- **Verification**: Manual insert via REPL confirming rows persist and the unique constraint works.
- **Risks**: Schema change requires running `wb init-db` in dev to pick up the new table.

## Stage 2 – Indexer integration
- **Goal**: Update the comment indexing script to mark request-like comments by upserting a `promotion_queue` attribute (`{"status":"pending","reason":"…","run_id":"…"}`).
- **Dependencies**: Stage 1 helpers; existing detection logic.
- **Changes**: When heuristics classify a comment as request-like, call `upsert_comment_attribute(comment_id, 'promotion_queue', {...})`; skip if already completed.
- **Verification**: Run indexer on sample data and inspect attributes table to ensure pending entries appear with correct metadata.
- **Risks**: Additional DB writes; ensure they’re batched or executed within the existing session.

## Stage 3 – Promotion worker CLI
- **Goal**: Build `wb promote-comment-batch` (or similar) that scans `promotion_queue` attributes with `status=pending`, calls `promote_comment_to_request` (`source='indexer'`), and updates the attribute to `status=completed` (with `request_id`) or `status=failed` (with error message).
- **Dependencies**: Stage 2 data; `app/tools/comment_promotion_cli.py` pattern.
- **Changes**: New CLI command/module; robust try/except so failures log but don’t abort the batch; optionally support `--force` to re-run even if completed.
- **Verification**: Seed attributes manually, run the CLI, confirm requests are created and attributes updated.
- **Risks**: Large batches causing API rate limits; allow `--limit` option.

## Stage 4 – Visibility + cleanup
- **Goal**: Provide CLI commands (`wb promote-comment-queue list --status pending|failed`, `wb promote-comment-queue retry <comment_id>`) and optional cleanup to delete old completed entries.
- **Dependencies**: Stage 3 CLI module.
- **Changes**: Add listing and retry subcommands; document workflow in README. Optionally schedule cleanup (remove completed entries after N days).
- **Verification**: Manual CLI use to list/retry; ensure cleanup doesn’t remove pending entries.
- **Risks**: CLI bloat; keep commands minimal but functional.
