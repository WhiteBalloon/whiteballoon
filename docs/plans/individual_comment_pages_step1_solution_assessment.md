## Problem
Members and operators can reference comments across search results and chats, but there is no canonical URL that loads a single comment outside of the full request thread, making it hard to share or audit specific conversations.

## Option A – Anchor links on request detail only
- Pros: Quick win; reuses existing `/requests/{id}` page with `#comment-{id}` anchors and optional highlight JS.
- Cons: Requires the sharer to know the parent request ID; large threads still need to load everything; search/services without request context (admin tooling, exports) can’t build the URL without an extra lookup.

## Option B – Dedicated `/comments/{id}` page that embeds context (recommended)
- Pros: Provides a stable permalink per comment, works for member/admin flows, can show the comment plus lightweight request + author context without loading the full thread; search endpoints can link directly once they know the comment ID.
- Cons: New route/template plus permission checks to ensure the viewer can see both the comment and its parent request.

## Option C – Admin-only comment inspector
- Pros: Minimal exposure; only admins see `/admin/comments/{id}` with moderation controls, leaving member UX unchanged.
- Cons: Does not help regular members share/comment references; duplicative UI vs. request detail and introduces a separate moderator-only surface.

## Recommendation
Adopt **Option B**. A small `/comments/{id}` page keeps permalinks stable, works for both members and admins, and still links back to the full request for additional context. The route can reuse the existing comment serialization and request metadata to avoid duplicating presentation logic while giving operator tooling a simple target URL.
