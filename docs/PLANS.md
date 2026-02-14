# PLANS.md — How to Read and Write Execution Plans

## Plan File Format

Each plan lives at `docs/exec-plans/active/<slug>.md` while in progress.
When complete, it moves to `docs/exec-plans/completed/<slug>.md`.

Plans are versioned by appending `-v2`, `-v3` etc. to the slug when replanned.

## Required Fields

```markdown
# Plan: <Title>

**Status:** active | paused | blocked | completed
**Domain:** <agent | lint | repo_index | harness | tests>
**Last Updated:** YYYY-MM-DD
**Owner:** <agent role or human name>

## Objective
One paragraph. What problem does this solve?

## Steps
- [ ] Step 1 description
- [x] Step 2 description (completed)
- [ ] Step 3 description

## Acceptance Criteria
- Criterion 1
- Criterion 2

## Risk
<low | medium | high> — brief justification

## Notes
Any context, blockers, or decisions made during execution.
```

## Agent Rules

- An agent MUST update `Last Updated` when it touches a plan
- Plans in `active/` older than 7 days trigger GP-009 violation
- Never delete a plan — move to `completed/` instead
- A plan's `Steps` section is the source of truth for progress

## Creating a Plan

1. Write the plan to `docs/exec-plans/active/<slug>.md`
2. Reference the plan in the task context so all agents in the workflow see it
3. Update step checkboxes as work completes
4. On completion, move to `docs/exec-plans/completed/`
