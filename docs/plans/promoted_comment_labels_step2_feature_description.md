## Problem
Requests created via comment promotion drop the LLM insight tags/labels that informed the promotion, so team members reviewing the new request lack that context unless they manually hunt down the original comment.

## User Stories
- As an admin, I want promoted requests to show the original comment’s LLM analysis so I can triage quickly without leaving the request page.
- As a moderator, I want a direct link from a promoted request back to the source comment so I can audit the conversation if needed.
- As a requester whose comment was promoted, I want others to see the categorized tags (topic, urgency, etc.) so the intent isn’t lost.

## Core Requirements
- Detect when a request originated from a comment promotion (via `comment_promotions`).
- Fetch the LLM analysis for that source comment using `comment_llm_insights_service.get_analysis_by_comment_id`.
- Render the analysis (summary, topics, resource/request tags, urgency, sentiment) in a dedicated panel on the request detail page, along with a link to `/comments/{id}`.
- Panel is visible to every viewer who can load the request; hide it only if no promotion/analysis exists or the viewer lacks permission to see the comment.

## Shared Component Inventory
- `app/routes/ui/__init__.py` request detail context: extend to include `promoted_comment_insight` payloads when relevant.
- `templates/requests/detail.html` / `requests/partials/item.html`: add a new card/section (similar styling to existing cards) using existing meta-chip styles.
- `comment_llm_insights_service`: reuse serialization helpers already used for comment insight badges.

## Simple User Flow
1. Request page loads and detects a `comment_promotions` row linking to comment 42.
2. Server queries the comment insight record for comment 42 and injects it into the template context.
3. UI shows a “Derived from Comment #42” card with tags/summary plus a “View comment” link.
4. If no insight exists, the card doesn’t render.

## Success Criteria
- Promoted requests show the original comment analysis (when available) without additional clicks.
- Users can jump to `/comments/{id}` from the panel.
- Requests not derived from comments remain unchanged.
- No PII leaks: viewers inherit the same access as the host request, so everyone who can see the request can see the panel.
