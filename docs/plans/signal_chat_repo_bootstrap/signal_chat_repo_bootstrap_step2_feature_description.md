# Signal Chat Repo Bootstrap – Step 2 Feature Description

**Problem**: Volunteers and analysts need a safe, repeatable way to convert Signal chat exports into structured, privacy-preserving datasets that can feed WhiteBalloon’s coordination features without touching production infrastructure.

**User Stories**
- As a data steward, I want to ingest a new Signal export with one command so I can keep shared archives up to date.
- As a privacy reviewer, I want deterministic hashing/redaction so I can prove no sensitive data leaves the secure workstation.
- As an analyst, I want enriched insights (topics, stats) so I can answer coordination questions quickly.
- As an integration engineer, I want bundles/APIs with explicit schemas so I can import chat-derived data into WhiteBalloon without reverse-engineering.

**Core Requirements**
- Provide CLI workflow covering ingest → normalize → privacy filter → enrich → publish, with resumable steps.
- Enforce configurable privacy policies and encrypted storage for raw exports.
- Emit normalized datasets (SQLite/Parquet) plus manifests/traces for lineage.
- Offer plug-in enrichment framework with at least baseline topic + participant stats modules.
- Package outputs as signed bundles and/or serve via read-only API for downstream syncing.

**Shared Component Inventory**
- CLI conventions from `./wb`: reuse command ergonomics but implement as standalone `signal-pipeline` entry point (extension of shared CLI concept).
- Pydantic schema patterns already used in WhiteBalloon models: extend them so cross-project contracts stay consistent.
- Sync bundle manifest structure from existing `*.sync.txt`: cite as inspiration but create new manifest optimized for chat data.

**Simple User Flow**
1. User clones repo, runs `make bootstrap` to install deps and fetch sample configs.
2. User runs `signal-pipeline ingest path/to/export.zip` to register a batch and verify checksums.
3. User runs `signal-pipeline normalize --batch <id>` to populate canonical tables.
4. Privacy reviewer runs `signal-pipeline privacy audit --batch <id>` and approves redactions.
5. User triggers `signal-pipeline enrich --batch <id>` followed by `signal-pipeline publish --batch <id>` to create bundle/API outputs.
6. Integration engineer consumes bundle or queries API, referencing manifest docs.

**Success Criteria**
- First public release ingests at least two distinct Signal export formats end-to-end without manual edits.
- Privacy audit command reports zero policy violations for approved batch before publishing.
- Published bundle re-imported into a sample WhiteBalloon instance without schema mismatches.
- Contributor onboarding time <30 minutes (clone → bootstrap → run sample pipeline).
