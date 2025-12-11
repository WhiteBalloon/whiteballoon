## Stage 1 – Routing + permission plumbing
- **Goal**: Add `/comments/{comment_id}` route that loads the comment, parent request, and viewer/session details.
- **Dependencies**: `app/routes/ui/__init__.py`, `request_comment_service`, `_build_request_detail_context` permission logic.
- **Changes**: Query `RequestComment` + `HelpRequest` by ID; reuse existing visibility checks (reject pending/private requests unless allowed); serialize comment via `request_comment_service.serialize_comment`; load author display name and avatar.
- **Verification**: Hit `/comments/{valid}` and `/comments/{missing}` in dev, ensuring access rules mirror `/requests/{id}`.
- **Risks**: Missing permission parity could leak hidden comments; mitigate by reusing existing helper functions.

## Stage 2 – Template + layout reuse
- **Goal**: Render a lightweight comment page using canonical components.
- **Dependencies**: Stage 1 data payload; `templates/partials/comment_card.html`, existing request summary markup.
- **Changes**: Create `templates/comments/detail.html` that includes the comment card (read-only variant) plus a request summary card with status + “View full request” link; add HTML title/meta updates.
- **Verification**: Manually open the page on desktop/mobile, ensure comment renders identically to request detail, and the request summary links correctly.
- **Risks**: Duplicated styles; keep layout simple (stacked cards) and reuse existing classes.

## Stage 3 – Linking + navigation polish
- **Goal**: Expose permalinks wherever comments surface.
- **Dependencies**: Stage 2 template; comment lists/search results.
- **Changes**: Update comment card context (`partials/comment_card.html` consumers) to include “Permalink” actions when appropriate (e.g., request detail, browse comments); ensure admin search tools can build `/comments/{id}` links without extra data.
- **Verification**: Click permalink buttons from at least one request page + browse search entry; ensure they load the standalone page and back-link to full request.
- **Risks**: Extra buttons clutter comment cards; consider icon-only link or use existing meta chip styling.
