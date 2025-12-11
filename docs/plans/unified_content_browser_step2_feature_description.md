## Problem
Requests, comments, and profiles live on separate pages with no shared search/filter UI, so users/admins can’t quickly browse or find content across the whole instance.

## User Stories
- As a community member, I want one “Browse” page where I can search keywords and instantly see matching requests, comments, or profiles.
- As an admin, I want to filter the same page by content type, status, or tags to triage faster.
- As a profile reviewer, I want to click into a profile tab without losing the current search or filters.

## Core Requirements
- Add a `/browse` page with a global search/filter bar (keyword field + facets like content type, status, tags).
- Default view: combined feed (requests/comments/profiles in chronological order) with clear labels per content type.
- Tabs (Requests | Comments | Profiles) reuse existing list partials but respect the same query params so switching tabs maintains filters.
- Pagination per tab/feed; combined view paginates the merged results.
- Server-rendered (no SPA) but progressive enhancement (optional JS to switch tabs without full reload).

## Shared Component Inventory
- `templates/requests/partials/item.html`, `templates/requests/partials/comment.html`, profile list partials – reuse for each tab.
- `app/routes/ui/__init__.py` – new route/handler that aggregates content and handles search/filter params.
- `static/css/app.css` / skin files – layout for tabs, combined feed, and filter bar.
- Optional: `static/js/browse.js` for tab enhancements.

## Simple User Flow
1. User opens `/browse`, sees search box + filters and combined feed.
2. Types “groceries” → page reloads with matching items across all content types, tabs show counts.
3. Clicks “Comments” tab → same filters applied but only comments shown.
4. Adds filter (e.g., tag=urgent) → URL updates (`/browse?query=groceries&tag=urgent&type=comments`), list refreshes.
5. Clears filters via “Reset” button.

## Success Criteria
- Combined feed returns mixed results with clear type labels and links.
- Tabs reflect the same filters and counts; switching tabs preserves query params.
- Search/filter bar works across all content types; filters are bookmarkable via query string.
- No regressions to existing request/profile pages.
