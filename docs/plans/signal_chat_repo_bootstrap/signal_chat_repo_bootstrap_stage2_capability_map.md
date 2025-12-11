# Signal Chat Repo Bootstrap – Stage 2 Capability Map

| Capability | Scope | Dependencies | Acceptance Tests |
| --- | --- | --- | --- |
| Export Intake & Validation | Detect supported Signal export formats, unpack archives, and register batches with metadata + checksums. | None | Given a `.zip` or directory export, CLI command registers batch, stores manifest, and surfaces validation report with zero unclassified files. |
| Canonical Normalization Layer | Parse conversations, participants, messages, reactions, and attachments into typed models with lineage references. | Export Intake | Running normalization on sample exports produces populated SQLite/Parquet tables whose row counts match Source metadata, and schema validation passes. |
| Privacy & Security Filter | Apply deterministic hashing/redaction to PII, encrypt raw exports at rest, and enforce secret-scoped config. | Normalization | Sensitive fields flagged in policy are transformed or encrypted; audit command shows zero unredacted PII before publishing. |
| Enrichment & Insight Engine | Run pluggable enrichment steps (topic tags, participant stats, summarizations). | Normalization, Privacy Filter | Enrichment pipeline adds derived tables/files with timestamps and references; reruns are idempotent and diff-able. |
| Distribution & Integration Layer | Package normalized/enriched data into shareable bundles or serve via lightweight API for downstream systems. | All previous | `publish` command emits bundle + manifest ready for import into WhiteBalloon or external tools, verified via checksum. |
| Developer Tooling & CI | Provide repo scaffolding, documentation, tests, linting, and fixtures for contributors. | Export Intake | Fresh clone can run `make bootstrap` (or similar) to install deps, lint, and execute sample pipeline successfully. |

## Dependency Graph
1. Export Intake & Validation → 2. Canonical Normalization Layer → 3. Privacy & Security Filter → 4. Enrichment & Insight Engine → 5. Distribution & Integration Layer. Developer Tooling & CI spans all stages but must exist early to host fixtures/tests.
