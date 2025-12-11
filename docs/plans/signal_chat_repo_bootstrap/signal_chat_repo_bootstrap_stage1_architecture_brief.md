# Signal Chat Repo Bootstrap – Stage 1 Architecture Brief

## Option A – Local Pipeline Orchestrator
- Structure repository as a Python package plus CLI (`signal-pipeline`) that stages ingestion, normalization, enrichment, and publishing through composable commands.
- Store parsed data in SQLite/Parquet files inside a versioned `storage/` directory, with manifests describing every export batch.
- Leverage `pydantic` models to define the canonical schema and auto-generate JSON/CSV exports for downstream tools.
- Trade-offs: simple ops and reproducibility, but long-running tasks depend on a single machine and offer limited concurrency.

## Option B – Evented Worker Mesh
- Split repo into FastAPI service + background workers; load Signal archives, push events to a queue (Redis/Kafka), and let workers normalize/enrich/publish asynchronously.
- Persist normalized data inside Postgres; expose REST endpoints for WhiteBalloon core to sync.
- Trade-offs: scalable and closer to production topology, but heavier infra requirements, more setup friction for volunteers, and introduces stateful services that need ops coverage.

## Option C – Notebook-first Exploration
- Keep the repo as a collection of Jupyter notebooks plus helper modules that parse Signal exports and materialize derived datasets on demand.
- Encourage analysts to iterate quickly, snapshot results into Git-tracked artifacts, and gradually promote reusable pieces into modules.
- Trade-offs: great for discovery but fragile for automation, harder to enforce consistent data contracts, and slow to integrate with CI/CD.

## Recommended Direction
Adopt **Option A – Local Pipeline Orchestrator**. It balances reproducibility, privacy, and contributor friendliness while leaving room to embed orchestrators (e.g., Taskflow/Airflow) later if needed.

## Existing Components to Reuse
- WhiteBalloon’s existing CLI scaffolding (`./wb`) demonstrates how to structure multi-command entry points; replicate patterns without coupling repos.
- Reuse existing Pydantic-based schemas for people/requests where applicable so cross-project sync remains straightforward.
- Borrow text-classification utilities from `wb/ai` (if licensable) to bootstrap enrichment steps.

## Data Contracts To Touch
- Define canonical models for `Conversation`, `Participant`, `Message`, `Attachment`, `Event`, and derived `Insight` payloads.
- Emit bundle manifests referencing Signal export filenames, hashed participants, and processing timestamps.
- Provide optional JSON API contract for downstream ingestion (mirrors `wb` sync payloads but specific to chat-derived data).

## Open Questions
- What minimal metadata must remain unhashed for deduplication (e.g., Signal IDs vs. contact names)?
- Which enrichment tasks (topic modeling, summarization, entity linking) are essential for MVP vs. later add-ons?
- Should we provide an optional lightweight UI for reviewing parsed exports, or rely solely on structured data dumps?
