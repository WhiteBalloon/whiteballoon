# WhiteBalloon Modular Spec – Planning Notes

## Stage 0 – Problem Framing seeds
- Problem: trust-driven mutual aid network lacking reproducible spec.
- Pain points: identity verification, privacy scopes, manual sync, limited AI guidance.
- Success metrics: growth of verified nodes, request fulfillment speed, sync integrity rate.
- Guardrails: FastAPI + SQLModel stack, server-rendered UX, signed sync bundles, privacy scopes.

## Stage 1 – Architecture Options outline
- Option A: Monolithic FastAPI app with modular routers (current).
- Option B: Service-split (auth, requests, sync) connected via message bus.
- Need to highlight data contracts: SQLModel tables, `/api/requests`, `.sync/*.sync.txt`, Dedalus MCP tools.
- Reuse: `./wb` CLI, templates, SQLModel definitions, docs/spec.md.

## Stage 2 – Capability Map draft
1. Trust Onboarding & Session Security – invites, login, verification, session cookies.
2. Mutual Aid Request Lifecycle – requests feed, detail views, comments, API.
3. Member Profiles & Directory – profile pages, invite graph, admin directory.
4. Federation & Sync Control – bundle exports, peers, CLI + UI ops.
5. AI Copilot & Recommendation Layer – Dedalus MCP tools, admin UI assistant.

Columns to fill: capability, scope, dependencies, acceptance tests.

## Stage 3 – Implementation Playbook seeds
- For each capability capture tasks, data/API, rollout, QA, fallback, instrumentation.
- Feature flags/ops: `.env` toggles (SITE_URL, SYNC_*), `ENABLE_COPILOT`, per-request `sync_scope`, CLI flags.
