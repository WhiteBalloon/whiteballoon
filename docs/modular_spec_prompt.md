# Modular Project Spec Prompt

Use this prompt when you need an AI coding assistant to generate a fresh, modular project specification that future assistants can apply to build similar systems from scratch. Paste everything between the code fences into the assistant, along with any project-specific context you have already gathered.

```
You are preparing a modular project specification so future coding assistants can rebuild this product (or create a sibling project) from an empty repository. Produce a Markdown document that:

1. Starts with a "Stage 0 – Problem Framing" section covering:
   - Problem statement (2-3 sentences)
   - Current pain points (bullets)
   - Success metrics (bullets)
   - Guardrails/constraints (bullets)

2. Adds a "Stage 1 – Architecture Options" section that:
   - Lists at least two viable architecture options with trade-offs
   - Highlights reusable components or prior art to borrow
   - Identifies data contracts/APIs touched and any open questions
   - Ends with a recommended direction and rationale

3. Includes a "Stage 2 – Capability Map" table with columns:
   - Capability name
   - Scope summary
   - Dependencies
   - Acceptance tests/definition of done
   Order the rows so downstream capabilities depend on upstream ones.

4. Provides a "Stage 3 – Implementation Playbook" subsection for each capability from Stage 2. Each subsection must document:
   - Tasks/work items required
   - Data/API changes (or explicitly state "None")
   - Rollout & ops considerations
   - Verification/QA guidance
   - Fallback/recovery plan
   - Instrumentation/observability notes

5. Closes with a "Feature Flags & Operational Modes" section describing any toggles, environment variables, or operator workflows that govern optional modules.

Author guidance:
- Keep the spec modular: the Stage 2 table and Stage 3 subsections should map 1:1 so teams can adopt capabilities independently.
- Call out privacy/security expectations explicitly if data leaves local storage.
- When referencing existing docs, cite file paths so future assistants know where to look for detail.
- Be concise (≤3 pages) but complete enough that a senior engineer could start implementation without additional meetings.
- Use Markdown headings, tables, and bullet lists for clarity; avoid code unless defining data contracts makes a section clearer.
```
