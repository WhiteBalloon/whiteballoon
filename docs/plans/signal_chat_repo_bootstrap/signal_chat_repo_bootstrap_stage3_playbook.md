# Signal Chat Repo Bootstrap – Stage 3 Implementation Playbook

## Capability: Export Intake & Validation
- Tasks: scaffold repo structure; create `signal_pipeline` package; implement CLI entry-point with `ingest` command; add format detectors for Signal `.zip` + directory exports; write checksum + manifest generator; seed fixtures from anonymized exports.
- Data/API changes: introduce `BatchManifest` model (JSON + sqlite table) storing source path, checksum, created_at, and schema version.
- Rollout/Ops: CLI command writes to local `storage/batches/<uuid>`; include dry-run flag; document how to rotate encryption keys for raw exports.
- Verification: unit tests for detectors; integration test running `ingest` on sample export; manual check ensures manifests capture file counts.
- Fallback: keep raw exports untouched; if parsing fails, flag manifest status `invalid` and store error log.
- Instrumentation: structured logs per batch, including detection path + counts; optional Sentry hook (env gated).

## Capability: Canonical Normalization Layer
- Tasks: define Pydantic models; create `normalize` CLI stage; write parsers for Signal `messages.csv`, attachments, profile images; map to relational tables; ensure lineage linking message→batch.
- Data/API changes: `Conversation`, `Participant`, `Message`, `Attachment`, `Reaction` tables; include `source_checksum`, `signal_id`, `hashed_contact` fields.
- Rollout/Ops: run `normalize` on batches flagged `ready`; store sqlite db under `storage/normalized/<batch_id>.db` with view for merges.
- Verification: deterministic row counts vs manifest; schema migration tests; sample query coverage.
- Fallback: if schema mismatch occurs, keep partial results in staging db and mark manifest `needs-mapping`.
- Instrumentation: log per-table counts; add `--profile` flag to emit timing stats.

## Capability: Privacy & Security Filter
- Tasks: define policy file enumerating sensitive fields; implement hashing/encryption utilities; extend normalization pipeline to apply transforms; add audit CLI (`privacy audit`).
- Data/API changes: `PrivacyPolicy` config, hashed contact columns, encryption key storage via `.env` references; audit report JSON.
- Rollout/Ops: require `PRIVACY_POLICY_PATH` in env; command fails fast if key missing; document secure storage of `.env`.
- Verification: unit tests for hashing; run audit command ensures zero policy violations; manual spot-check hashed data vs original on secure machine.
- Fallback: `privacy audit --export` writes sample rows for manual review under encrypted dir; pipeline halts until compliance fixed.
- Instrumentation: log counts per privacy action; optionally emit metrics to StatsD if env configured.

## Capability: Enrichment & Insight Engine
- Tasks: create plug-in registry; implement baseline enrichers (topic tagging via keywords, participant stats, timeline histogram); add `run enrich` CLI; support incremental reruns via state table.
- Data/API changes: `EnrichmentJob` metadata, derived tables (`MessageTopic`, `ParticipantStats`, `ConversationSummary`).
- Rollout/Ops: default enrichers enabled; allow `--only` to run targeted jobs; store outputs in `storage/enriched/` with version tags.
- Verification: tests covering idempotency; manual run verifying derived tables exist; add sample notebooks showcasing outputs.
- Fallback: failed job marks manifest `partially-enriched`; reruns skip completed enrichers.
- Instrumentation: log job duration + row deltas; optional tracing span wrappers.

## Capability: Distribution & Integration Layer
- Tasks: implement `publish` CLI to assemble normalized/enriched data into bundle (tarball + manifest); optionally spin up FastAPI read-only API; create `sync` spec doc; add importer stub for WhiteBalloon core.
- Data/API changes: `BundleManifest` schema referencing dataset files, hashing, feature flags; optional REST endpoints `/bundles`, `/messages`, `/insights`.
- Rollout/Ops: signed bundles stored under `dist/`; API runs locally behind auth token; document handshake for WhiteBalloon import.
- Verification: checksum validation when re-loading bundle; contract tests verifying API responses match schema.
- Fallback: keep last known good bundle; `publish --verify` ensures compatibility before release.
- Instrumentation: log bundle sizes, publish duration, API access metrics.

## Capability: Developer Tooling & CI
- Tasks: configure Poetry + Make targets; add lint/format/test GitHub Action; provide `.devcontainer` or `uv` instructions; seed example configs; create CONTRIBUTING guide.
- Data/API changes: none beyond repo metadata.
- Rollout/Ops: bootstrap script installs dependencies, downloads sample exports (public dummy data), and runs `ingest+normalize+enrich` smoke test.
- Verification: CI badge green; `make check` passes locally; docs describe workflow end-to-end.
- Fallback: add troubleshooting doc; pin dependency versions to prevent drift.
- Instrumentation: track CI duration, test coverage, and artifact sizes.

## Feature Flag Strategy
- `SIGNAL_PIPELINE_ALLOW_API` toggles FastAPI server exposure.
- `ENABLE_EXPERIMENTAL_ENRICHERS` gates ML-heavy enrichments until privacy reviewed.
- `ALLOW_RAW_STORAGE` ensures exports are encrypted before storing unless explicitly disabled for dev fixtures.
