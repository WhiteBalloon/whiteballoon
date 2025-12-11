## Problem
Members and admin-operators frequently spot actionable needs inside comment threads, but turning those comments into full `HelpRequest` records requires manual copy/paste across forms and cannot be triggered remotely by MCP agents.

## User Stories
- As a member reading a request thread, I want to click "Promote to request" on a comment so I can turn emerging needs into trackable tasks without rewriting details.
- As an admin-operator, I want to promote any comment (even from another user) and tweak the title/status before publishing so the feed stays organized.
- As an MCP agent, I want an authenticated API that accepts a comment ID and returns the new request so automations can escalate promising comments.
- As a reviewer, I want promotion actions to be logged/audited so we can trace who escalated which comment if questions arise.

## Core Requirements
- Provide a backend service/endpoint (e.g., `POST /comments/{id}/promote`) that validates permissions, pre-fills request fields from the comment, and returns the created request payload.
- Add UI affordances on comment cards for members/admins to trigger promotion, including a confirmation modal with editable fields (title, description, scope, status).
- Ensure MCP/MCS clients can call the same endpoint via the existing MCP server tooling with proper auth tokens and CSRF protections where applicable.
- Record audit metadata (who promoted, when, source comment ID) accessible to admins via existing logs or request detail views.
- Prevent duplicate promotions by tracking if a comment already spawned a request, while allowing manual overrides when intentionally creating multiple derived requests.

## Shared Component Inventory
- **Comment card (`templates/requests/partials/comment.html`)** – extend this canonical component to show the promote action when the viewer has permission; no new standalone UI.
- **Request creation service (`app/services/request_service.py` or equivalent)** – reuse the existing request creation logic so promotions follow the same validation rules and tagging.
- **Admin audit/log surface (`templates/admin/` + `storage/comment_llm_runs`)** – reuse existing logging infrastructure (e.g., `RequestLog`, CLI logs) to capture promotion events instead of inventing a new logger.
- **MCP server tools (in `tools/` or `wb`)** – add a new MCP command referencing the shared API instead of a custom code path.

## Simple User Flow
1. User (member or admin) views a request comment thread.
2. They click "Promote to request" on a comment; a modal opens with pre-filled title/description derived from the comment text plus optional metadata (links to original request/comment).
3. User edits fields as needed, selects scope/status, and confirms; the UI calls the backend promotion endpoint.
4. Backend validates permissions, creates the new `HelpRequest`, logs the promotion event, and returns data.
5. UI shows success, links to the new request, and flags the original comment as promoted (with link) to avoid duplicate work.
6. MCP agent flow: agent invokes MCP tool with comment ID + optional overrides; tool calls the same endpoint and surfaces the created request ID back to the agent.

## Success Criteria
- ≥90% of promotions reuse the inline UI button (measured via logs) within 2 weeks of launch.
- MCP server can promote at least 10 comments in a row without manual intervention, verified in staging.
- Every promoted request links back to the source comment ID for traceability (UI + DB field).
- Duplicate promotion attempts warn the user and require explicit confirmation before creating another request.
- Audit logs record promoter identity, timestamp, and source comment for all actions.
