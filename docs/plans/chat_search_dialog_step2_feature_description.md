## Problem
The request detail page always renders the "Search chat" section expanded, even when there are zero or only a handful of comments. This adds visual noise, suggests functionality that can’t produce results, and forces users to collapse it manually.

## User Stories
- As a requester reading a short thread, I don’t want an empty search panel taking over the page when there’s nothing to search.
- As a moderator, I want the chat search control to stay discoverable on busy threads but start collapsed so the conversation remains the focus.
- As a developer building MCP agents, I want a clear indicator (e.g., threshold-based rendering) so agents don’t trigger searches on empty threads.

## Core Requirements
- Only render the chat search panel when the total comment count meets a configurable minimum (default 5) and the thread has at least one comment.
- When the panel is rendered, load it in a collapsed state with a simple toggle to expand/collapse without losing functionality.
- Preserve existing search behavior (queries, tags, participant filters) once expanded; no backend changes required beyond telling the template whether it should render.
- Ensure accessibility: toggles use buttons with correct labels/ARIA so keyboard users can expand the panel.

## Shared Component Inventory
- `templates/requests/detail.html` – extend the existing search panel markup; no new template.
- `static/js/request-chat-search.js` – add minimal JS to handle collapse toggle, reusing existing initialization where possible.
- `app/routes/ui/__init__.py` – reuse existing context builder to pass `comment_count` and threshold flags; no new API routes.

## Simple User Flow
1. Request detail page loads comment list; backend computes total comments.
2. If total comments < threshold (default 5) or zero, the chat search panel is omitted entirely.
3. If threshold is met, show the panel collapsed under a "Search chat" header with an expand button.
4. User clicks expand → panel reveals search form (input, participant/topic filters) and behaves as today; clicking collapse hides it again.

## Success Criteria
- Threads with fewer than 5 comments show no chat search module.
- Threads with ≥5 comments show the module collapsed by default and expand/collapse reliably without reloading the page.
- No regressions to existing search functionality (queries return the same results once expanded).
- Accessibility: toggle is focusable, has an ARIA label, and screen readers announce collapsed/expanded state.
