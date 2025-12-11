# Modular Project Spec Process

Use this checklist before running the modular project spec prompt so every assistant follows the same workflow and produces interchangeable deliverables.

## 1. Discovery & Inputs
- Inventory all existing project documentation (README, specs, planning docs) and note which pieces must be reused vs. replaced.
- Capture the primary goal, target users, and any non-negotiable constraints (stack, deployment boundaries, privacy requirements).
- Identify candidate modules/capabilities—start with high-level flows (auth, data ingestion, sync, admin tooling) and refine as needed.
- Determine which reusable assets (schemas, CLI patterns, infra scripts) should be referenced in the new spec.

## 2. Draft Planning Skeleton
- List Stage 0–3 sections and the capability rows you expect the assistant to fill.
- For each capability, jot down seed bullets for tasks, data contracts, rollout notes, and guardrails so the assistant has anchors.
- Decide how feature flags or operational modes should be represented; note environment variables, CLI toggles, or UI switches.

## 3. Run the Prompt
- Provide the assistant with:
  - Project summary + constraints gathered during discovery
  - Any mandatory references or prior specs to emulate
  - The `Modular Project Spec Prompt` text (copy/paste from `docs/modular_spec_prompt.md`)
- Ask the assistant to draft the complete spec in Markdown following the prompt structure.

## 4. Review & Iterate
- Verify Stage 0–3 coverage is complete and modular (1:1 mapping between Stage 2 rows and Stage 3 subsections).
- Check that success metrics, guardrails, and feature flags are actionable and testable.
- Ensure all referenced files/commands exist or add TODOs for missing assets.
- Request revisions if trade-offs, acceptance tests, or fallback plans are unclear.

## 5. Publish & Maintain
- Commit the final spec under `docs/specs/<project_name>_modular.md` (or another agreed location) with clear version history.
- Update the spec whenever new capabilities ship or constraints change; keep Stage 2 table current so downstream teams can plan work.
- Cross-link the spec from onboarding docs (`AI_PROJECT_GUIDE.md`, `README.md`) so future assistants can find it quickly.
- Log follow-up tasks (e.g., feature flag implementation, schema updates) in the project tracker to maintain alignment between docs and code.
