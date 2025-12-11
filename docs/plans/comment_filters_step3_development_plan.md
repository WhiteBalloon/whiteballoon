## Stage 1 – Backend filter plumbing
- **Goal**: Parse query params (e.g., `tag`, `urgency`, `status`) on the request list route, filter the query accordingly, and expose available filter options + selected values to the template.
- **Dependencies**: `app/routes/ui/__init__.py` list handler, request list query logic.
- **Changes**: Extend the DB query to handle optional filters, compute distinct tags/urgency counts for the filter UI, and include context keys like `filter_options` and `active_filters`.
- **Verification**: Manual test by hitting `/` with `?tag=grocery&urgency=urgent` and confirming the list shrinks appropriately.
- **Risks**: Query performance; ensure indexes/where clauses are simple.

## Stage 2 – Responsive filter UI
- **Goal**: Add a filter partial used on request list pages that renders chips/controls differently based on viewport (top bar vs sidebar).
- **Dependencies**: Stage 1 context; templates `templates/requests/index.html` (and any other list views).
- **Changes**: Create `templates/requests/partials/filter_bar.html` with sections for tags, urgency, status. Insert it on list pages. Add CSS for mobile bar (`display:flex`, horizontal scroll) and desktop sidebar (sticky column). Provide “Reset filters” link.
- **Verification**: Manual browser test (mobile + desktop) to ensure layout adapts and doesn’t break the list.
- **Risks**: CSS conflicts; ensure new classes are namespaced.

## Stage 3 – Filter interactions + accessibility
- **Goal**: Ensure chip toggles update the query string cleanly and remain keyboard accessible.
- **Dependencies**: Stage 2 markup.
- **Changes**: Implement chip links or small forms that toggle filters (no heavy JS required initially). Add proper aria-labels, focus styles, and optionally progressive enhancement (JS to prevent full reload). Update README/docs to mention filter capabilities.
- **Verification**: Keyboard-only test toggling filters; confirm query params update as expected and pagination preserves them.
- **Risks**: Complex multi-select states; scope to manageable facets first.
