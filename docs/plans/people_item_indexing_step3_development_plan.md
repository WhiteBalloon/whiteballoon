## Stage 1 – Warehouse landing tables + ingestion hooks
- **Goal**: Persist all relevant Signal/chat/comment insight data into warehouse tables (`raw_signal_messages`, `raw_request_comments`, `comment_insights`) with lineage + CDC markers.
- **Dependencies**: Existing Signal import + comment ingestion jobs; warehouse connectivity/credentials.
- **Changes**:
  - Extend ingestion jobs to emit structured events (e.g., via Pub/Sub) consumed by the ETL runner.
  - Define warehouse schemas, clustering keys, and freshness timestamps.
  - Backfill historical data to seed baseline indexes.
- **Verification**: Run ETL for a sample day and confirm row counts match source DB; validate schema via warehouse queries.
- **Risks**: Warehouse cost spikes if backfill is inefficient; CDC drift if ingestion lags.
- **Components/APIs**: Signal import pipeline, comment ingestion service, warehouse ETL runner.

## Stage 2 – Build warehouse `people_index` / `request_index` transforms
- **Goal**: Materialize normalized docs per user/request (bios, tags, stats, embeddings metadata, freshness/version fields).
- **Dependencies**: Stage 1 tables populated.
- **Changes**:
  - Write SQL/DBT transforms that aggregate raw tables into index tables.
  - Compute derived metrics (top tags, reaction counts, participant lists) and attach bios/proof points from existing snapshot data.
  - Store embedding payload references (vector store ID or serialized arrays) plus schema version.
- **Verification**: Spot-check transformed docs for a handful of users/requests; ensure counts match raw data; unit-test transforms if using DBT.
- **Risks**: Large docs breaching warehouse column limits; schema drift when upstream adds new fields.
- **Components/APIs**: Warehouse transform layer, signal snapshot metadata, comment insight tables.

## Stage 3 – Expose internal indexing API backed by warehouse
- **Goal**: Provide a service endpoint (e.g., `/api/index/{people|requests}`) that reads warehouse docs and returns JSON with freshness + version metadata.
- **Dependencies**: Stage 2 tables ready; service authentication plumbing.
- **Changes**:
  - Build a lightweight API service (FastAPI/Flask) running near the warehouse to fetch docs with caching.
  - Implement auth (service tokens) and pagination/filtering (by tag, location, etc.).
  - Add monitoring/logging for request volume and latency.
- **Verification**: Integration test hitting the API for sample IDs; measure latency; confirm auth rejects unauthorized callers.
- **Risks**: Latency if API queries heavy docs; auth misconfiguration exposing data.
- **Components/APIs**: New indexing API service, warehouse connection pool, existing auth service (for token validation).

## Stage 4 – Synchronize app-side caches/components with API
- **Goal**: Update app services (profile glazing, chat search, suggestions) to source data from the indexing API and refresh local caches when versions change.
- **Dependencies**: Stage 3 API stable; feature flag strategy.
- **Changes**:
  - Extend `request_chat_search_service` and profile highlight loaders to fetch docs + store JSON blobs with version metadata.
  - Add background job to poll for updates and invalidate stale caches.
  - Wire feature flags to fall back to legacy caches during rollout.
- **Verification**: Manual smoke across a few profiles/requests ensuring richer facets load; log checks confirming cache refreshes triggered.
- **Risks**: Cache stampede if polling misconfigured; inconsistent data if version checks fail.
- **Components/APIs**: Chat search indexer, profile glaze pipeline, suggestion service, background job scheduler.

## Stage 5 – Monitoring, access controls, and rollout support
- **Goal**: Ensure observability, quota protections, and operator tooling are ready for production use.
- **Dependencies**: Stages 1-4 complete.
- **Changes**:
  - Add dashboards/alerts for ETL freshness, API latency, cache staleness, and warehouse costs.
  - Implement RBAC enforcement in the API and document how operators/auth services request access.
  - Prepare rollback plans + documentation for operators and analysts.
- **Verification**: Alert simulations, access audit, runbook review.
- **Risks**: Missing alerts hiding staleness; over-permissive access tokens.
- **Components/APIs**: Observability stack, indexing API, ops runbooks.
