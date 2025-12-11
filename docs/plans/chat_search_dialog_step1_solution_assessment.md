## Problem
The request detail page always renders the "Search chat" panel expanded, even when threads have only a handful (or zero) comments, cluttering the UI and inviting searches that will never return results.

## Option A – Hide chat search when there are too few comments
- Pros: Simplest UX; removes the panel entirely when comment count is below a threshold (e.g., <5) so the layout stays focused on discussion.
- Cons: Users lose a consistent entry point; panel suddenly appears once the threshold is crossed, which may be jarring.

## Option B – Collapse chat search by default with conditional rendering
- Pros: Keeps the control discoverable while reducing clutter: render the panel only when comments exist, but show it collapsed so low-volume threads still look clean. Users can expand when needed.
- Cons: Requires JS/HTML tweaks for the collapsible state; still shows an empty affordance on tiny threads if not hidden.

## Option C – Always show but display a "not enough comments" message
- Pros: Minimal code change; lets users know search is unavailable because there isn't enough history yet.
- Cons: Leaves the bulky UI visible even when useless; still invites clicks that go nowhere.

## Recommendation
Adopt **Option B**: render the chat search panel only when a minimum comment threshold is met (e.g., ≥5), and when rendered, load it collapsed by default. This balances cleanliness with discoverability—small threads stay tidy, while larger ones still expose the search affordance without dominating the page.
