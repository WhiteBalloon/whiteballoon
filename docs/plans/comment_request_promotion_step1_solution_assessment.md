## Problem
Comments often contain actionable requests, but there is no streamlined way for members or admin-operators (including MCP agents) to convert a comment into a formal help request without retyping details.

## Option A – Inline promotion inside request/comment UI
- Pros: Minimal context-switch; reuse existing request creation logic by pre-filling fields from the comment; supports members promoting their own or others' comments when permissions allow.
- Cons: Still needs a backend surface (API/service) for reuse; MCP automation would require duplicating logic unless paired with Option B.

## Option B – Promotion service + shared API (UI + MCP)
- Pros: Introduces a dedicated service/endpoint (e.g., `POST /comments/{id}/promote`) that both UI actions and MCP tools can call; centralizes validation, auditing, and deduping; easy to gate by role regardless of comment ownership.
- Cons: Requires plumbing new API and CSRF/ACL handling, plus frontend wiring for manual promotion buttons.

## Option C – Staging queue via task worker
- Pros: Allows asynchronous review (operator approves promotions later), reducing accidental spam; MCP agents can enqueue drafts without blocking.
- Cons: Adds queues, new UI, and latency before a request becomes live; overkill for the immediate promotion workflows desired.

## Recommendation
Adopt a **hybrid of Option A + Option B**. Implement the shared promotion service/API as the canonical path, then expose it through inline UI affordances so members or admins can promote any relevant comment (not just their own) while also enabling MCP agents to call the same endpoint. This keeps logic centralized while delivering a seamless manual workflow.
