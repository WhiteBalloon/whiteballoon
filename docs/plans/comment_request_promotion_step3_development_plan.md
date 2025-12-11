## Stage 1 – Promotion service + API skeleton
- Goal: Introduce a backend service function and API route (REST + MCP) that can turn a comment into a HelpRequest while reusing existing request creation logic.
- Dependencies: Existing `app/modules/requests/services.create_request`, `RequestComment` models, Step 2 requirements.
- Changes: Add service helper (e.g., `promote_comment_to_request(session, comment_id, actor, overrides)`) handling validation, duplicate detection, audit logging; expose HTTP route `POST /comments/{id}/promote` returning new request payload; ensure MCP server tool can call same logic.
- Verification: Manual API call via authenticated HTTP client (e.g., httpie) promoting sample comment; confirm request appears in DB and response includes link back to comment.
- Risks: Permission bugs allow unauthorized promotion; duplicate promotions without guard.
- Canonical components: Reuse request creation service, audit logging mechanism (job tracker/realtime logs).

## Stage 2 – UI affordances + confirmation modal
- Goal: Surface "Promote to request" action on comment cards for eligible viewers with modal to edit fields before submission.
- Dependencies: Stage 1 API ready; comment card template partial.
- Changes: Update `templates/requests/partials/comment.html` + relevant JS to show button, load modal, pre-fill title/description, submit to promotion endpoint with CSRF token; add inline badge linking to promoted request when available.
- Verification: Manual browser test as member/admin promoting comments; ensure modal displays, request created, UI updates.
- Risks: CSRF issues, modal regressions, duplicate buttons.
- Canonical components: Comment card partial, existing form/JS helpers for modals.

## Stage 3 – MCP tool wiring + logging
- Goal: Add MCP server tool definition so agents can call the promote endpoint and ensure audit trails/logging capture all sources.
- Dependencies: Stage 1 service; Stage 2 optional for manual users.
- Changes: Extend MCP server config/tool list with `promote_comment_to_request` action hitting backend API; include parameters for comment ID + overrides; enhance logging (e.g., realtime job log or admin log) to note source (UI vs MCP) and store actor info; optionally expose feed in admin UI.
- Verification: Run MCP agent command promoting comment; check logs, DB entry, link to comment.
- Risks: MCP auth misconfiguration, missing audit trail.
- Canonical components: Existing MCP server harness (`tools/`), admin log surfaces.

## Stage 4 – Duplicate handling + UX polish
- Goal: Prevent accidental re-promotions and ensure traceability between original comment and new request.
- Dependencies: Stage 1-3.
- Changes: Track promotion metadata (e.g., store `promoted_request_id` on comment or linking table); show UI badge referencing existing request; API warns when comment already promoted with opt-in override flag; add tests (manual) verifying warnings.
- Verification: Promote comment twice—first flows normally, second surfaces warning and requires override parameter; UI indicates promoted state.
- Risks: Schema change may be required if metadata missing (try to reuse existing fields first); race conditions.
- Canonical components: Comment detail partial, request detail linking logic, audit/event log.
