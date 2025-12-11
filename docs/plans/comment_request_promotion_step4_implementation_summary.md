# Comment Request Promotion – Step 4 Implementation Summary

## Stage 1 – Promotion service + API skeleton
- **Shipped**: Added `comment_request_promotion_service.promote_comment_to_request` to build new `HelpRequest` rows from existing comments, plus `/api/comments/{id}/promote` so authenticated users (UI or agents) can call the shared logic. Response reuses the canonical `RequestResponse` schema and logs each promotion via the service logger.
- **Verification**: Ran a manual Python script to seed a temporary comment and confirmed the service created/deleted a promoted request successfully (`python - <<'PY' ...`).

## Stage 2 – UI affordances + confirmation modal
- **Shipped**: Added a "Promote" action to request comment cards (respecting the same permission check as the API) and rendered a lightweight `<dialog>` modal that pre-fills the comment text, lets the reviewer tweak summary/contact/status, and POSTs to the shared `/api/comments/{id}/promote` endpoint via the new `static/js/comment-promotion.js` helper.
- **Verification**: Loaded a request detail page locally, promoted a seeded comment via the modal, and confirmed the browser redirected to the newly created request.

## Stage 3 – MCP tool wiring + logging
- **Shipped**: Added a reusable CLI (`wb promote-comment` → `app.tools.comment_promotion_cli`) that promotes comments via the shared service with explicit actor attribution and source labels. Updated the Dedalus MCP verification script to expose a `promote_comment_to_request` tool (in addition to the audit tool) so agents can escalate comments, and plumbed a `source` flag through `comment_request_promotion_service` logs to distinguish UI, CLI, and MCP usage.
- **Verification**: Seeded temporary users/comments via a Python script, ran `python -m app.tools.comment_promotion_cli --comment-id ... --actor ...`, and confirmed the JSON response contained the new request ID. Manually inspected Dedalus CLI prompt/tool list to ensure the new tool is registered when `--promote-comment-id` is provided.

## Stage 4 – Duplicate handling + UX polish
- **Shipped**: Added the `comment_promotions` table plus service helpers so every promotion stores `comment_id ↔ request_id` metadata. The API/CLI now guard against accidental duplicates (409 with promoted request link) unless a caller passes `force`. Request comments render a “Promoted to request #…” badge and the modal warns/asks for override when a comment already has promotions. The MCP helper exposes `--promote-force` and UI wiring forwards the `force` flag when users intentionally re-promote.
- **Verification**: Scripted a comment promotion, verified the second attempt hit the 409 guard, then retried with `allow_duplicate=True` to produce a second request. In the browser, promoted a comment, observed the badge/link rendering, and confirmed the modal shows the duplicate warning plus override checkbox before submitting another request.
