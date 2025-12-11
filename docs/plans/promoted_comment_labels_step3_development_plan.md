## Stage 1 – Backend wiring
- **Goal**: Load promoted-comment metadata + LLM insight when viewing a request.
- **Dependencies**: `comment_request_promotion_service`, `comment_llm_insights_service`, request-detail context builder.
- **Changes**: Query `CommentPromotion` by `request_id` inside `_build_request_detail_context`; if present, fetch the source comment + insight (`get_analysis_by_comment_id`) and package the relevant fields (summary, tags, urgency, sentiment, resource tags, run metadata, comment permalink) into the context.
- **Verification**: Manually promote a comment, open the new request as both an admin and a regular viewer, and confirm context contains the insight payload; verify non-promoted requests don’t trigger extra DB reads.
- **Risks**: Extra queries could slow request pages; keep lookups bounded (single promotion per request) and guard missing insight gracefully.

## Stage 2 – UI panel
- **Goal**: Present the insight on the request detail page.
- **Dependencies**: Stage 1 context data; existing card styles/meta chips.
- **Changes**: Add a “Derived from comment” card in `templates/requests/detail.html` (or a partial) showing comment info, summary, tags, urgency badge, and link to `/comments/{id}` using existing `meta-chip` classes.
- **Verification**: Load a promoted request as any viewer (admin/member/requester) and ensure the card renders responsively; confirm regular requests show no card.
- **Risks**: Visual clutter—keep the card collapsible/simple and reuse styles so it blends with existing layout.

## Stage 3 – Optional exposure (if needed)
- **Goal**: Surface insight data in other contexts (e.g., admin dashboards or browse feed entries) only if low effort.
- **Dependencies**: Stage 1 payloads.
- **Changes**: If helpful, add small badges (e.g., “Derived from comment”) in combined feeds linking back to the insight card.
- **Verification**: Spot-check whichever surfaces are updated.
- **Risks**: Scope creep; skip if Stage 2 already meets goals.
