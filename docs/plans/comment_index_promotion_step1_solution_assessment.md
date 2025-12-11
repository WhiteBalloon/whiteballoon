## Problem
We want the comment indexing workflow to auto-promote request-like comments into HelpRequests. Today, operators still run ad-hoc scripts, so promising needs stay buried.

## Option A – Extend indexing with in-memory queue + file log
- Pros: Avoids DB changes; indexing writes candidate entries to a JSONL file that a separate worker reads.
- Cons: Harder to inspect/query; file-based state is brittle and lacks referential integrity.

## Option B – Add a generic `comment_attributes` table and store promotion metadata there
- Pros: Reuses the existing attribute pattern (similar to `user_attributes`), giving us a structured DB-backed queue without inventing a new table type per feature.
- Cons: Requires a migration to introduce the attributes table; storing queue state in a generic key/value table is slightly indirect.

## Option C – Dedicated `comment_promotion_queue` table (schema change)
- Pros: Tailored schema (status, run_id, etc.) that’s easy to query and reason about.
- Cons: Adds a new table/migration; more surface area to maintain.

## Recommendation
Since we want a DB-backed queue but would prefer not to add a bespoke table, choose **Option B**: introduce a `comment_attributes` table (mirroring `user_attributes`) and store staged promotion metadata as attribute rows (e.g., key `promotion_pending`, JSON value). Indexing writes/updates those entries; the promotion worker reads attributes, calls the existing promotion service, then flips/removes the attribute. This keeps the schema change minimal/reusable and avoids file-based queues.
