## Problem
Operators can’t run “who/what helped” searches because people/request indexes only store lightweight chat tokens and bios. We need a richer, centralized index (powered by the analytics warehouse) that captures structured facts and exposes them back to the app with low-latency caches where necessary.

## User Stories
- As an operator, I want to search for people who shared medical resources in LA so I can re-engage the right helpers quickly.
- As a requester support lead, I want to pull every request involving housing logistics in the last 14 days so I can spot trends and gaps.
- As a product engineer, I want a single API to fetch indexed signals (bios, tags, embeddings) so UI features don’t re-implement scraping logic.
- As a data analyst, I want the warehouse to be the source of truth so I can run BI dashboards without new ETL jobs per feature.

## Core Requirements
- Stream Signal snapshots, chat comments, and LLM insights into the analytics warehouse with normalized schemas for people and requests.
- Materialize per-person and per-request index documents (bios, stats, embeddings, related IDs) inside the warehouse and expose them through an internal API.
- Provide freshness metadata plus schema versioning so downstream caches know when to invalidate.
- Support optional low-latency caches (JSON blobs) for UI surfaces by syncing from the warehouse API.
- Enforce access controls so only authorized services/operators can read the indexed data.

## Shared Component Inventory
- `ChatSearchIndex` (request detail page search panel): will consume the new API to hydrate richer metadata but continue rendering via existing component.
- People profile pages (`templates/profile/show.html`): reuse current bio/highlight component but source data from the warehouse-backed API.
- Admin insights dashboards (existing analytics views): extend them to query the warehouse tables; no new UI component required.
- Request suggestion chips (related-request sidebar): continue using the canonical suggestion component but feed it warehouse-powered similarity scores.

## User Flow
1. Signal/chat ingestion lands raw events → ETL loads them into warehouse tables.
2. Warehouse transformations build `people_index` and `request_index` docs (including embeddings and metadata).
3. An internal API exposes these docs plus freshness/version info.
4. App services (profile glazing, chat search, suggestions) fetch the docs, refresh local caches, and render existing UI components.
5. Operators use UI/search to explore richer indexed data; analysts query the warehouse directly for deeper cuts.

## Success Criteria
- ≥95% of people/request pages load data sourced from the warehouse index (verified via logs) within 2 weeks of launch.
- Warehouse tables update within 15 minutes of new Signal/chat data landing (p95 latency).
- Operators can filter people/requests by at least three new facets (location, resource tag, request tag) without manual queries.
- Data analysts can run warehouse SQL to answer “helpers per resource tag” without additional ETL.
