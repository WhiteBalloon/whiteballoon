# Signal Chat Repo Bootstrap

This repo blueprint defines `signal-pipeline`, a standalone toolkit that ingests Signal chat exports and emits privacy-preserving bundles for WhiteBalloon and allied projects.

## Why this exists
Grassroots organizers often coordinate through Signal chats, but the exports are messy, privacy-sensitive, and difficult to reuse. This repository captures the tooling, data contracts, and workflows required to turn those exports into structured, shareable datasets without touching WhiteBalloon’s production stack.

## What’s inside
- **Planning artifacts**: Stage 0–3 complex-feature docs and Step 1–3 feature planning (see `docs/plans/`) describe the architecture, capabilities, and development plan.
- **Pipeline stages** (to be implemented): `ingest`, `normalize`, `privacy audit`, `enrich`, and `publish` commands wired through the `signal-pipeline` CLI.
- **Data contracts**: Canonical schemas for conversations, participants, messages, attachments, reactions, enrichment outputs, and bundle manifests.
- **Privacy guardrails**: Deterministic hashing, encryption-at-rest for raw exports, audit tooling, and documentation for reviewers.
- **Distribution layer**: Signed bundle generator plus optional FastAPI read-only API for downstream consumers.

## Getting started (future repo)
1. Clone the forthcoming repository and run `make bootstrap` (or `uv run bootstrap.py`) to install dependencies, set up the virtualenv, and download anonymized sample exports.
2. Register a batch: `signal-pipeline ingest fixtures/sample_export.zip`.
3. Normalize and apply privacy policies: `signal-pipeline normalize --batch <id>` followed by `signal-pipeline privacy audit --batch <id>`.
4. Run enrichers: `signal-pipeline enrich --batch <id>`.
5. Publish a bundle or start the read-only API: `signal-pipeline publish --batch <id>` or `SIGNAL_PIPELINE_ALLOW_API=1 signal-pipeline serve`.

## Key references
- `docs/plans/signal_chat_repo_bootstrap_stage0_problem.md`
- `docs/plans/signal_chat_repo_bootstrap_stage1_architecture_brief.md`
- `docs/plans/signal_chat_repo_bootstrap_stage2_capability_map.md`
- `docs/plans/signal_chat_repo_bootstrap_stage3_playbook.md`
- `docs/plans/signal_chat_repo_bootstrap_step1_solution_assessment.md`
- `docs/plans/signal_chat_repo_bootstrap_step2_feature_description.md`
- `docs/plans/signal_chat_repo_bootstrap_step3_development_plan.md`

These artifacts must be approved and committed in order before implementation begins, per `FEATURE_DEVELOPMENT_PROCESS.md`. Future iterations will add the Step 4 implementation summary once code ships.
