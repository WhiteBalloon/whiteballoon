## Problem
When an admin promotes a comment into a full request, the new request loses the LLM-generated labels (topics, urgency, tags) that helped justify the promotion, leaving reviewers without that context on the request page.

## Option A – Inline note on request header
- Pros: Minimal UI; shows a short badge (e.g., “Promoted from Comment #123 · Tags: housing, urgent”) near the request metadata.
- Cons: Limited room; hard to display structured data like multiple tag categories or insights details.

## Option B – Dedicated “Derived from comment” panel (recommended)
- Pros: Adds a collapsible card on the request detail page that fetches the source comment + its LLM analysis (topics, urgency, resource tags) via `comment_llm_insights_service`, exposes it to every viewer of the request (not just admins), and includes a link back to the original comment.
- Cons: Requires extra query when loading the request and careful phrasing so the data is understandable to all viewers.

## Option C – Background enrichment (copy labels onto request record)
- Pros: Makes labels first-class request fields, so existing request filters can reuse them.
- Cons: Requires schema changes (new columns/table) and duplication of data; labels could go stale if the underlying comment is reprocessed.

## Recommendation
Go with **Option B**. Keep the authoritative labels with the original comment/insights record, but surface them via a request-side panel that everyone can see, ensuring promoted requests retain the same tagged context that justified them.
