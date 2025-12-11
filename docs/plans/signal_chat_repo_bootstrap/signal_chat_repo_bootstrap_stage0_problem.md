# Signal Chat Repo Bootstrap – Stage 0 Problem Framing

## Problem Statement
WhiteBalloon needs a dedicated repository that can ingest, normalize, and analyze Signal chat export files so that conversations, trust cues, and resource requests from grassroots mutual-aid groups become queryable inputs for future coordination tools.

## Current Pain Points
- Signal archives live as ad-hoc `.zip` / `.csv` bundles with inconsistent schemas, making repeatable ingestion difficult.
- There is no canonical location for storing parsed messages, participants, and attachments independent of the main app, so experimentation risks destabilizing production data.
- Operators manually scrub personal info before sharing exports, slowing down onboarding of new volunteers and increasing privacy risk.
- Analysts lack scripted workflows to derive metadata (topics, contacts, timelines) that could plug into WhiteBalloon’s AI layer.

## Success Metrics
- 100% of supported Signal export formats parse into normalized records with lineage metadata.
- New exports can be processed end-to-end (ingest → enrich → publish) in <10 minutes on a laptop with no manual cleanup.
- Sensitive fields are redacted or deterministically hashed before storage, with opt-in access policies documented and enforced.
- Downstream WhiteBalloon services can subscribe to emitted bundles or API endpoints without custom glue code.

## Guardrails
- No proprietary dependencies: rely on Python stdlib + permissive OSS so the repo can be shared with community responders.
- Keep personally identifiable data encrypted or hashed at rest; embed privacy review checkpoints in every stage.
- Favor flat-file storage (Parquet/SQLite) over managed cloud services so the repo runs offline.
- Limit initial scope to Signal exports (no WhatsApp/Telegram) but design interfaces so new transports can plug in later.
