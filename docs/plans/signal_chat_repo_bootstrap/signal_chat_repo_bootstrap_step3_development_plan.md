# Signal Chat Repo Bootstrap – Step 3 Development Plan

1. **Repository + CLI Scaffold**
   - Goal: Initialize Python package, project layout, and `signal-pipeline` CLI entry point with placeholder commands.
   - Dependencies: None.
   - Changes: Create Poetry project (or uv), `signal_pipeline` module, `storage/` directories, basic logging config, `signal-pipeline --help` command registration.
   - Verification: `signal-pipeline --help` lists subcommands; lint + unit tests for CLI wiring pass.
   - Risks: Over-scoping initial tooling; mitigate by pinning to minimal dependencies.
   - Components/APIs: Establish CLI conventions (aligned with WhiteBalloon `./wb`).

2. **Batch Manifest + Sample Fixtures**
   - Goal: Support `ingest` command that records batch metadata and validates Signal export structure.
   - Dependencies: Stage 1.
   - Changes: Implement manifest model + sqlite table, checksum utilities, fixture loader with anonymized sample exports, manifest status tracking.
   - Verification: Run `signal-pipeline ingest fixtures/sample_export.zip` and inspect manifest JSON; add unit tests for checksum + detector.
   - Risks: Real exports may vary; capture unknown files in manifest for manual review.
   - Components/APIs: `BatchManifest` schema; alignment with future bundle manifest.

3. **Canonical Normalization Pipeline**
   - Goal: Parse exported CSV/attachments into strongly typed tables with lineage references.
   - Dependencies: Stage 2.
   - Changes: Implement `normalize` command, Pydantic models for conversation/participant/message/attachment/reaction, sqlite writer, row-count summary.
   - Verification: Fixture run populates tables with expected counts; schema validation tests pass.
   - Risks: Schema drift between Signal versions; add mapping layer + version gating.
   - Components/APIs: Canonical conversation/message schemas mirroring WhiteBalloon data contracts where possible.

4. **Privacy Policy Engine**
   - Goal: Enforce hashing/redaction/encryption policies across normalized data and raw storage.
   - Dependencies: Stage 3.
   - Changes: Add policy config file, deterministic hash utility, encryption helper for raw exports, `privacy audit` command with report + exit codes.
   - Verification: Running audit on fixture yields zero violations; tests cover hashing/encryption; manual decrypt round-trip validated.
   - Risks: Hash collisions reducing dedupe accuracy; maintain salt rotation guidance.
   - Components/APIs: Privacy policy spec (JSON/YAML) consumed by CLI; hashed fields align with WhiteBalloon privacy expectations.

5. **Enrichment Framework**
   - Goal: Provide plug-in interface + baseline enrichers (topic tags, participant stats, conversation summary).
   - Dependencies: Stage 4.
   - Changes: Define `Enricher` protocol, registry, persisted job metadata, CLI `enrich` command, derived tables for topics/stats/summaries.
   - Verification: Fixture batch obtains derived tables; rerunning `enrich` is idempotent; unit tests for enrichers.
   - Risks: Enrichers might leak sensitive data; ensure they consume already-redacted datasets only.
   - Components/APIs: Derived schemas documented for downstream consumption.

6. **Distribution Layer (Bundles + API)**
   - Goal: Package outputs as signed bundles and optional FastAPI read-only endpoints for downstream ingestion.
   - Dependencies: Stage 5.
   - Changes: Implement `publish` CLI, bundle manifest writer, checksum/signature tool, FastAPI server (behind feature flag) exposing `/bundles`, `/messages`, `/insights` backed by sqlite views, importer stub for WhiteBalloon core.
   - Verification: Published bundle re-imported and validated; API contract tests run via pytest; sample WhiteBalloon importer script successfully ingests dataset.
   - Risks: Bundle size/performance; provide streaming writer + compression options.
   - Components/APIs: Bundle manifest spec referencing canonical schemas; FastAPI endpoints align with WhiteBalloon integration expectations.

7. **Developer Tooling & Documentation**
   - Goal: Finalize README, CONTRIBUTING, bootstrap script, CI workflow, and privacy practices doc.
   - Dependencies: Parallel to Stages 1-6 but finalize after core features land.
   - Changes: Documentation updates, `make bootstrap` (or `uv run bootstrap.py`), GitHub Actions for lint/test, example notebooks.
   - Verification: Fresh clone instructions succeed; CI green; docs reference all commands.
   - Risks: Docs drift; add doc-check step in CI.
   - Components/APIs: README + docs referencing CLI and bundle manifests.
