## Problem
Request feeds showcase tags/topics but users can’t click them to filter the list, so discovering related requests requires manual searching or scrolling.

## Option A – Inline filters on each request card
- Pros: Simple to implement; clicking a tag filters just that card or anchors to matching comments.
- Cons: Doesn’t help when users want a broader feed filter; redundant work per page.

## Option B – Shared filter bar on request list pages (chosen)
- Pros: Adds a reusable filter bar (topics, tags, urgency) to `/` (and other list feeds) that updates query params and filters the result set. Keeps the request detail page uncluttered, but gives discoverability at the feed level.
- Cons: Requires extending the list endpoints/queries to respect filter params; needs UX adjustments on list pages only.

## Option C – Full-screen modal with saved views
- Pros: Richer UX with multi-select, saved filter sets, and cross-request context.
- Cons: Overkill for current scope; more design and persistence complexity.

## Recommendation
Pursue **Option B**: implement a filter bar on the requests list/feed pages only, backed by query parameters so seasoned users can bookmark/share filtered views while keeping individual request pages unchanged.
