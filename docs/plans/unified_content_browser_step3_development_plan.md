## Stage 1 – Backend query plumbing
- **Goal**: Add `/browse` route that loads requests, comments, and profiles based on query params (keyword, type filters, pagination).
- **Dependencies**: Existing request/comment/profile list queries.
- **Changes**: Create helper functions to fetch filtered data per type; parse query params (e.g., `q`, `type`, `tag`, `status`). Build combined feed (sorted by date) plus tab-specific data and counts.
- **Verification**: Manual dev-run hitting `/browse`, `/browse?type=comments`, etc., ensuring data matches filters.
- **Risks**: Query performance; ensure filters use indexes or limit results.

## Stage 2 – Template layout + filter bar
- **Goal**: Build `templates/browse/index.html` with global filter bar, combined feed list, and tabs.
- **Dependencies**: Stage 1 data; existing partials.
- **Changes**: Create filter bar partial (keyword input + facets), render tabs with counts, include combined feed using new partials (type badges, metadata). Reuse request/comment/profile partials for tab content.
- **Verification**: Manual browser test (desktop + mobile) toggling filters/tabs; ensure layout looks good.
- **Risks**: CSS conflicts; ensure new styles are scoped.

## Stage 3 – Tab interactions + progressive enhancement
- **Goal**: Keep tabs functional without JS while optionally adding JS to switch tabs without reload.
- **Dependencies**: Stage 2 markup.
- **Changes**: Use anchor links with query params for tabs; highlight active tab. Optionally add a small JS snippet to intercept tab clicks and swap content for snappier UX.
- **Verification**: Keyboard-only test switching tabs, verifying query params update; confirm no JS still works.
- **Risks**: Complexity creep; keep JS minimal/optional.

## Stage 4 – Combined feed polish & accessibility
- **Goal**: Ensure mixed results clearly show type labels, icons, and accessible text; add “view details” links per type.
- **Dependencies**: Stage 2 combined feed.
- **Changes**: Add badges (e.g., “Request”, “Comment”, “Profile”), include snippet/summary for each content type, ensure ARIA roles/labels on tabs/filter bar.
- **Verification**: Screen-reader/keyboard test; manual check that each item links to the right detail page.
- **Risks**: Visual clutter; prioritize readability.
