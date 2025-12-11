## Stage 1 – Backend flags + threshold constant
- **Goal**: Pass a `chat_search_enabled` flag to the template based on total comment count.
- **Dependencies**: Existing `_build_request_detail_context`, `request_comment_service.list_comments`.
- **Changes**: Add a constant (e.g., `CHAT_SEARCH_MIN_COMMENTS = 5`) in the UI route, compute the total comments once, and include booleans like `can_show_chat_search` and `chat_search_collapsed_by_default` in the context.
- **Verification**: Add temporary unit/integration log or manual check to ensure the flag flips when a thread crosses the threshold.
- **Risks**: Counting comments multiple times; ensure we reuse the total count already computed for pagination.

## Stage 2 – Template + JS collapse toggle
- **Goal**: Update `templates/requests/detail.html` and `static/js/request-chat-search.js` to respect the new flags.
- **Dependencies**: Stage 1 flags.
- **Changes**: Wrap the search module in a conditional; add a collapse/expand button and `data` attributes (e.g., `data-chat-search-panel`). Default state is collapsed via CSS class or hidden attribute. Update JS to initialize only when the panel is present and to handle toggling.
- **Verification**: Manual browser test on threads with <5, =5, and >5 comments to confirm visibility/toggle behavior; confirm search still works once expanded.
- **Risks**: CSS layout regressions; ensure toggled panel doesn’t break on mobile.

## Stage 3 – UX polish + accessibility
- **Goal**: Ensure the toggle is keyboard-accessible and stateful (ARIA attributes) and update docs if needed.
- **Dependencies**: Stage 2 markup.
- **Changes**: Add `aria-expanded`, `aria-controls`, focus styles; ensure collapsed state persists through page loads only via default (no local storage). Optionally update README/docs to mention the threshold behavior.
- **Verification**: Keyboard-only test; run accessibility inspector to ensure ARIA roles are valid.
- **Risks**: Forgetting to update translations/strings (none currently);
