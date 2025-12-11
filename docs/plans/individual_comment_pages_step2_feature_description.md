## Problem
Comments only live inside the request detail view, so operators and members cannot share a stable permalink or open a comment outside of its full thread.

## User Stories
- As a member, I want a `/comments/{id}` link that shows the exact comment so I can reference it in chat or invites.
- As an operator-admin, I want to open a comment page directly from search/moderation tools to review its context quickly.
- As a requester, I want to follow a shared comment link and still understand which request and author it belongs to.

## Core Requirements
- Add a `/comments/{comment_id}` route that loads the comment, its parent request metadata, and relevant permissions before rendering.
- If the viewer cannot access the request/comment (pending scope, private sync scope, or deleted), return 404/403 accordingly.
- Page layout must show the comment body, author identity, timestamps, scope badge, and a minimal request summary with a "View full request" link.
- Include shareable metadata (page title + canonical link) so copied URLs remain meaningful.
- Ensure existing feeds/search results can link to the new URL without schema changes.

## Shared Component Inventory
- `templates/partials/comment_card.html`: reuse or extend to render the canonical comment body block.
- `requests/partials/request_summary` (if available) or equivalent metadata rows from `templates/requests/detail.html`: provide request title/status snippet; avoid inventing a new markup style.
- `app/services/request_comment_service.serialize_comment`: reuse serialization to avoid duplicating payload formatting.

## Simple User Flow
1. User clicks a comment link (`/comments/123`) from search/chat.
2. Server loads the comment + request, validates visibility, and renders the page with comment + request summary.
3. User reads the standalone comment and optionally clicks “View full request” to jump into the full thread.

## Success Criteria
- `/comments/{id}` works for any visible comment and 404s for forbidden/deleted ones.
- Page shows all essential context (author, scope, timestamps, request summary, link back) without loading other comments.
- Existing search/moderation UIs can swap to the new permalink without extra queries.
- No regressions to request detail or comment creation flows.
