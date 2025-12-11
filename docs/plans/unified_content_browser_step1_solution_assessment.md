## Problem
Content (requests, comments, profiles) is scattered across different pages and tooling. Users and admins can’t easily browse or search everything from one place on the instance.

## Option A – Unified list page
- Pros: Build a single page with a global search/filter bar and a single combined feed of mixed content (requests + comments + profiles), giving an “everything” view.
- Cons: Can be noisy; needs strong visual cues to distinguish content types; filtering by type is essential.

## Option B – Tabbed browser sharing the same filters
- Pros: Provide tabs (Requests / Comments / Profiles) that reuse their existing list templates while sharing the same search/filter bar and query params. Users can quickly switch context without leaving the page.
- Cons: Requires extra UI scaffolding to keep tabs in sync with filters, but avoids the clutter of a single combined feed.

## Option C – Dedicated API + JS front-end
- Pros: Build a richer SPA-like experience with dynamic filtering across resources.
- Cons: Out of scope for current stack; higher complexity and maintenance.

## Recommendation
Combine **Option A + Option B**: Create a single “Browse” page that renders a unified search/filter bar, plus tabs. The default view shows a combined feed (sorted chronologically) so users see everything at once, while tabbed views show filtered lists per resource type. This keeps the UX cohesive while providing focused views when needed.
