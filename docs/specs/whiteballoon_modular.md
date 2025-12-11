# WhiteBalloon Modular Project Specification

## Stage 0 – Problem Framing
**Problem statement**
WhiteBalloon needs a reproducible blueprint for rebuilding its trust-driven mutual aid network so any team can stand up an invite-only community that coordinates care, syncs selectively, and layers AI assistance on top of a transparent social graph. Future contributors require clarity on the authentication chain, request lifecycle, federation primitives, and operator tooling to avoid regressions.

**Current pain points**
- Knowledge about invite flows, privacy scopes, and sync rituals is scattered across `README.md`, `docs/spec.md`, and planning notes, making onboarding slow.
- Operators struggle to reason about when data can safely leave an instance; guardrails exist in code but not in a unified spec.
- AI/Dedalus integrations depend on implicit contracts with MCP tools and admin routes, so reproducing them from scratch is error-prone.
- Federation behaviors (`*.sync.txt` bundles, CLI vs. UI workflows) lack crisp acceptance tests, risking drift between nodes.

**Success metrics**
- New engineers can recreate the baseline stack (FastAPI + SQLModel + vanilla SSR) and pass end-to-end auth/request tests in <2 days.
- ≥95% of requests honor their declared `sync_scope`, verified via automated export checks.
- Admins complete core jobs (approve member, triage request, run sync) within 3 clicks or CLI commands, even on fresh deployments.
- Mutual Aid Copilot suggestions achieve >80% operator satisfaction in tests documented under `docs/mutual_aid_copilot_proposal.md`.

**Guardrails / constraints**
- Keep the Python/FastAPI/SQLModel stack, `./wb` CLI tooling, and server-rendered templates described in `README.md` + `docs/spec.md`.
- Privacy defaults: data is local unless explicitly marked public; sync bundles stay signed and human-auditable.
- Progressive enhancement only; each workflow must have HTML form fallbacks and avoid SPA frameworks.
- External services (Dedalus MCP, email relays) must authenticate via `.env` secrets and respect least-privilege scopes.

## Stage 1 – Architecture Options
### Option A – Modular Monolith (current baseline)
- **Description**: Single FastAPI app (`app/main.py`) where modules register routers/services via `app/modules/__init__.py`. SQLModel manages persistence in one SQLite/Postgres database. CLI (`./wb`) coordinates setup, sync, and admin tasks.
- **Trade-offs**: Simple deployment, shared code paths, and straightforward SSR templating (`templates/`). Risk of tight coupling between auth, requests, and sync, but suits small teams and enables direct reuse of `docs/spec.md` schemas.
- **Reusable components**: `tools/dev.py` CLI commands, `app/models.py` for contracts, `static/css/app.css`, existing templates, `.sync` bundle format.
- **Data contracts/APIs**: `/auth/*`, `/api/requests`, `/admin/*`, Dedalus MCP tools hitting FastAPI routes, CLI commands invoking `app.services`. Open questions: Should AI actions mutate via HTTP or CLI? How to partition DB for multi-tenant nodes?

### Option B – Service-Sliced Core with Async Task Bus
- **Description**: Separate auth/trust service, request service, and sync/AI orchestrator communicating over a message queue (e.g., Redis streams or NATS) while sharing a canonical schema repo. Frontend remains SSR but proxies to individual services.
- **Trade-offs**: Improves fault isolation and horizontal scaling for heavy AI workloads, but introduces network hops and dev complexity. Requires duplicating pieces of the CLI or rethinking job orchestration.
- **Reusable components**: Same data contracts from `docs/spec.md`, but each service wraps them in its own FastAPI app; the `wb` CLI becomes a multi-target client.
- **Data contracts/APIs**: Shared SQLModel definitions become published packages; message schemas for sync jobs; HTTP APIs for each service. Open questions: How to maintain transactional boundaries across services? What new secrets/ACLs are required for event buses?

**Recommendation**
Adopt **Option A** with disciplined modular boundaries. It aligns with existing repos, minimizes lift for rebuilds, and keeps SSR + CLI workflows intact. Use clear module APIs (services + routers) to isolate auth, requests, sync, and AI so future teams can extract them later if scaling requires Option B.

## Stage 2 – Capability Map
| Capability | Scope summary | Dependencies | Acceptance tests / DoD |
| --- | --- | --- | --- |
| Trust Onboarding & Session Security | Invite issuance, registration, verification codes, session cookies, admin bootstrapping | FastAPI auth routes, SQLModel tables (`User`, `Invite`, `UserSession`), cookies, CLI helpers | New node can issue invite, register user, promote session to fully authenticated, and see correct nav states; verification codes rotate and log admins approving them |
| Mutual Aid Request Lifecycle | Feed, detail pages, comment threads, completion actions, JSON API | Auth capability, `Request`/`Comment` tables, `/api/requests` endpoints, templates, JS enhancements | Auth’d user creates request (open/pending), completes request via API/form, comments appear instantly, API returns scope-filtered payloads |
| Member Profiles & Directory | Profile pages, invite graph, admin directory, avatar & contact management | Auth capability, `Profile`, `InviteMapCache`, storage for avatars (`static/uploads`), admin ACLs | Admin sees `/admin/profiles`, members view `/members` with proper redactions, invite map renders for eligible viewers, avatars upload + display |
| Federation & Sync Control | `.sync` bundle builder, peer management, CLI + web control panel, signing keys | Requests/profiles data, `wb sync` CLI, `/admin/sync-control`, `.env` key storage, filesystem for bundles | Operator can add peer, run push/pull (CLI or UI) with signed bundles, scope toggles respected, exported manifests verifiable |
| AI Copilot & Recommendations | Dedalus MCP integration, admin UI agent, suggestion surfacing, safety guardrails | Auth, requests data, sync APIs, Dedalus credentials (`docs/mutual_aid_copilot_proposal.md`), background tasks | Admin launches copilot, invokes MCP tools (triage, scope toggle) with audit logs, latency within SLA, opt-out respected |

## Stage 3 – Implementation Playbook
### Capability 1 – Trust Onboarding & Session Security
- **Tasks / work items**
  - Implement invites (`POST /auth/invites`, `/invite/new`) with max-uses, auto-approval, personalization per `docs/spec.md`.
  - Build registration/login/verification flow with SSR templates and CLI fallbacks (`wb create-admin`, `wb session approve`).
  - Persist sessions in SQLModel, issue `wb_session_id` cookie, enforce role-based nav segments.
  - Document environment expectations in `README.md` and `.env.example` (e.g., `SITE_URL`, secret keys).
- **Data / API changes**: Tables (`User`, `Invite`, `InvitePersonalization`, `AuthenticationRequest`, `UserSession`) defined in `app/models.py`. APIs `/auth/register`, `/auth/login`, `/auth/login/verify`, `/auth/logout`. No additional external APIs.
- **Rollout & ops considerations**: First user bootstrap must be idempotent; ensure CLI can re-run `wb init-db`. Provide scripts to rotate invite secrets. Keep verification attempts rate-limited.
- **Verification / QA**: Automated tests covering invite creation, invite exhaustion, code verification, and session role transitions. Manual test for admin auto-promotion.
- **Fallback / recovery**: If verification fails, allow admins to approve via CLI or `/admin/sessions`. Provide `wb session deny` to clean stale attempts. Store invites in DB so they can be reissued.
- **Instrumentation / observability**: Log invite issuance, login attempts, and approval actions with user + IP metadata. Emit metrics for pending vs. approved sessions.

### Capability 2 – Mutual Aid Request Lifecycle
- **Tasks / work items**
  - Implement `/` dashboard with request form partials (`templates/requests/`), progressive enhancement JS for updates, and server-rendered fallback.
  - Provide `/requests/{id}` detail with comments, admin moderation controls, and shareable URLs.
  - Build JSON API under `/api/requests` (list/create/complete) mirroring `docs/spec.md` fields.
  - Wire completion + comment posting to respect roles and `sync_scope` toggles.
- **Data / API changes**: Tables `Request`, `Comment` (SQLModel). JSON schema documented in `docs/spec.md`. Ensure contact emails stored securely. No new external APIs.
- **Rollout & ops considerations**: Migrate existing data carefully when adding new statuses. Provide background job to promote pending requests after session approval.
- **Verification / QA**: Unit tests for request creation states, comment moderation, API filtering by scope. Browser tests to ensure JS + non-JS parity.
- **Fallback / recovery**: Provide CLI or admin tools to reopen requests, soft-delete comments, and restore from `.sync` exports.
- **Instrumentation / observability**: Track request counts by status, completion latency, and comment volume. Add audit log entries for moderation events.

### Capability 3 – Member Profiles & Directory
- **Tasks / work items**
  - Implement `/members`, `/profile`, `/people/{username}` views with role-aware redactions.
  - Build admin directory `/admin/profiles` with filters and drill-downs.
  - Add invite graph visualization (`/invite/map`) caching in `InviteMapCache`.
  - Support avatar uploads + contact editing under `/settings/account` using local storage.
- **Data / API changes**: Reuse `User`, `Profile`, `Invite`, `InviteMapCache` tables. Upload handling uses `static/uploads/`. No external APIs beyond optional CDN for avatars (default local only).
- **Rollout & ops considerations**: Enforce file-size/type limits. Provide cron/CLI to refresh invite maps. Document admin privacy responsibilities.
- **Verification / QA**: Tests for visibility rules (self vs. admin vs. member). Confirm invite map respects permissions. Manual QA for upload + rendering.
- **Fallback / recovery**: Allow admins to reset avatars via CLI or delete corrupted uploads. Cache invalidations if invite map data gets stale.
- **Instrumentation / observability**: Log directory queries, invite map generation time, and upload errors.

### Capability 4 – Federation & Sync Control
- **Tasks / work items**
  - Maintain `.sync/*.sync.txt` bundle format with signed headers (reference `docs/spec.md`).
  - Implement `/sync/public`, `/sync/scope`, and `/admin/sync-control` to manage peers, tokens, and job queueing.
  - Extend `wb sync` CLI (`tools/dev.py`) for push/pull, peer editing, and hub operations (`wb hub serve`).
  - Store signing keys and peer configs under `.sync/` with secure permissions.
- **Data / API changes**: Exports include subsets of `Request`, `Comment`, `User`, `Invite` per `sync_scope`. Web UI hits FastAPI endpoints for job creation; CLI writes to filesystem/temp dirs. Optional HTTPS upload when `wb sync push --url` is used.
- **Rollout & ops considerations**: Document manual review steps before pushing public data. Provide migration path for key rotation. Ensure background jobs resilient to interruption.
- **Verification / QA**: Integration tests comparing exported bundles to DB state, verifying signature chain, and replaying imports into clean DB. Smoke test UI queue buttons.
- **Fallback / recovery**: Keep previous bundles/version history in git for rollbacks. Provide `wb sync repair` or documented manual steps for partial imports.
- **Instrumentation / observability**: Log each job with actor, peer, duration, success/failure. Emit metrics for bundle sizes and scope counts.

### Capability 5 – AI Copilot & Recommendations
- **Tasks / work items**
  - Define Dedalus MCP tools (request triage, scope toggle, invite generator, sync prep) per `docs/mutual_aid_copilot_proposal.md`.
  - Embed copilot widget in `/admin` (or `/admin/sync-control`) with secure token exchange and UI affordances.
  - Create backend endpoints or CLI wrappers the MCP tools call (ensuring parity with manual workflows).
  - Document deployment steps for Dedalus credentials, rate limits, and opt-in/out toggles.
- **Data / API changes**: Introduce MCP tool schemas, optional `CopilotAudit` table logging invocations. APIs may expose summarized request metadata; ensure scopes filter to admin-only contexts. External dependency on Dedalus gateway.
- **Rollout & ops considerations**: Ship feature disabled by default, gated behind env var + admin toggle. Provide instructions for storing Dedalus keys in `.env` and verifying via `/admin/dedalus`.
- **Verification / QA**: End-to-end tests using stub MCP gateway, ensuring tool outputs align with manual results. Security review for data shared externally.
- **Fallback / recovery**: Allow admins to disable copilot instantly (env flag + UI). Keep manual CLI/UI workflows authoritative so operations continue without AI.
- **Instrumentation / observability**: Capture latency, success/failure per tool, and operator feedback (thumbs up/down). Log prompts/responses with PIIs scrubbed.

## Feature Flags & Operational Modes
- **Environment toggles**: `SITE_URL`, `SESSION_SECRET`, `SYNC_PUBLIC_SCOPE`, `ENABLE_COPILOT`, `DEDALUS_API_KEY`, `PREFERRED_HOST` documented in `.env.example`. Flags govern invite fallback domains, sync exposure, and AI availability.
- **Per-entity scopes**: `sync_scope` on requests/comments/users controls export eligibility and feeds both UI badges and bundle builders.
- **CLI modes**: `wb sync push|pull`, `wb hub serve`, and `wb skins` commands expose operational modes; ensure usage is documented in `README.md` and `docs/spec.md`.
- **Admin UI switches**: `/sync/scope` toggles public/private state; `/admin/dedalus` enables the copilot once credentials are verified.
- **Fail-safe defaults**: Copilot disabled unless explicitly configured, sync exports default to local storage, invites require admin creation post-bootstrap.

