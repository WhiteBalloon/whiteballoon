## Problem
The home feed (`/`) and other request list views display resource tags, urgency labels, and topics, but there’s no way to click those categories to filter the list. Users must scroll or manually guess search terms to find similar help requests.

## User Stories
- As a community member, I want to tap a “Groceries” or “Transportation” chip on the request feed so the list shows only requests in that category, even on mobile.
- As an ops reviewer on desktop, I want a persistent filter sidebar so I can toggle multiple facets without scrolling away from the list.
- As a staff engineer, I want filter state reflected in the URL query params so I can bookmark/share filtered feeds.

## Core Requirements
- Add a responsive filter component for request list pages only:
  - Mobile (≤ tablet width): render a horizontal filter bar at the top of the list, with chips that scroll horizontally if needed.
  - Desktop/wide screens: render the same filters in a sidebar adjacent to the list.
- Filters expose common facets (resource tags, urgency, status, etc.). Clicking toggles that filter, updates the URL query parameters (e.g., `?tag=grocery&urgency=urgent`), and reloads the list with filtered results.
- Support multi-select where sensible (e.g., multiple tags) and visibly highlight active filters with clear “Reset filters” affordances.
- Ensure pagination retains query params; filter state should persist across page loads.
- Keep request detail pages unchanged.

## Shared Component Inventory
- `templates/requests/index.html` – extend with a responsive filter component (top bar / sidebar). Consider extracting a partial (e.g., `templates/requests/partials/filter_bar.html`).
- `app/routes/ui/__init__.py` (list route) – parse incoming filter params, fetch the filtered request queryset, and provide the available filter options + current selections to the template.
- `static/css/app.css` – add responsive styles for bar vs sidebar layouts; optionally `static/js/request-feed.js` for progressive enhancement (chip toggles without manual form submission).

## Simple User Flow
1. Mobile user lands on `/` and sees a horizontal scrollable filter bar above the feed. Tapping “Groceries” reloads `/ ?tag=groceries`, highlighting the chip.
2. Desktop user sees a left sidebar with filter sections (tags, urgency, status). Clicking multiple chips toggles them on/off and reloads the feed with updated query params.
3. Pagination links include the active query params so the filtered view persists. “Reset filters” clears params and reloads the full feed.

## Success Criteria
- Filter component appears only on request list pages and adapts between bar (mobile) and sidebar (desktop) layouts without breaking the feed layout.
- Clicking/toggling filters updates the URL, reloads the list, and highlights the active selections.
- Pagination retains filters; clearing filters resets the list.
- No regressions to request detail pages or list performance.
