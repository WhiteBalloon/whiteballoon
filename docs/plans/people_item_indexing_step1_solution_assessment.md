## Problem
Current indexing only stores lightweight chat tokens/topics and ad hoc bios, making it hard to query or resurface rich people/request context later.

## Option A – Extend existing chat/person caches in place
- Pros: Reuses `ChatSearchIndex`/Signal snapshot pipelines; minimal new infra; incremental rollouts via schema versioning.
- Cons: JSON caches get heavier and harder to evolve; mixing raw chat data with persona docs risks coupling lifecycles; still requires bespoke fan-out jobs per surface.

## Option B – Build unified “people + items” index service backed by structured docs
- Pros: Central schema for people/request facts (LLM insights, tags, stats, embeddings); easier to power future search/recommendations; asynchronous worker can hydrate both sides from events.
- Cons: Requires new storage layer (e.g., doc table/blob) and ingestion job; higher up-front design effort; migration plan needed for existing caches.

## Option C – Push everything into analytics warehouse and query via API
- Pros: Offloads storage/querying to warehouse; can leverage BI tooling, SQL, and existing ETL patterns; no new app-side cache format.
- Cons: Higher latency for UI surfaces; depends on ETL freshness; warehouse permissions and costs add operational overhead.

## Recommendation
Choose Option C. Centralizing people/request facts in the analytics warehouse lets us lean on existing ETL + SQL tooling, unlock BI queries immediately, and expose the data back to the app via lightweight APIs/webhooks without inventing yet another cache format. Latency-sensitive views can still materialize denormalized snapshots, but the warehouse becomes the system of record for rich indexing.
