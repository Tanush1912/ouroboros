# FUTURE-FIXES.md — Known Risks and Deferred Work

Real issues identified during design review. These are not hypothetical — each one
will surface during implementation or early usage. Ordered by likelihood of blocking
progress.

---

## Real Risks to Address

### 1. Repo Index Freshness Problem

**The issue:**
`symbols.json` and `file_map.json` are generated "on every commit via CI." But agents
write files mid-workflow. Between `implement_node` and `validate_node`, the index is
stale. Any tool call to `search_symbol()` after a file has been written will return
incorrect locations or miss new symbols entirely.

**Why it bites early:**
The implementer writes files, then the validator runs `run_lint()`, which internally
calls `run_arch_lint()`, which calls `check_file()` — this is fine because arch lint
reads live files. But if the implementer writes a new class and the validator or
reviewer then calls `search_symbol()` to look it up, it will return `None`.

**Options:**
- **(a) In-memory index updates:** After each `write_file` tool call, patch the
  in-memory `symbols.json` dict with newly extracted symbols from the written file.
  Requires the tool to run AST extraction inline and update a module-level cache.
- **(b) `reindex(paths: list[str])` tool:** A lightweight tool the agent can call
  explicitly after writing. Runs `build_index.py` scoped to only the changed paths.
  Less magical, more explicit.

**Recommended approach:** Option (b). Register `reindex` in the `ToolRegistry` under
category `"index"`. The implementer's system prompt should instruct it to call
`reindex(files_changed)` as the last step of any write operation.

**Files to touch:**
- `repo_index/build_index.py` — add `reindex(paths)` entry point
- `agents/tools/fs.py` — add `reindex` tool wrapping it
- `agents/tools/registry.py` — register `reindex`
- `agents/workers/implementer.py` — add reindex instruction to system prompt

---

### 2. LangGraph + PydanticAI Integration Ambiguity

**The issue:**
LangGraph's native agent abstraction and PydanticAI's `Agent` class have overlapping
concepts: tools, state management, and execution loops. The plan implies using LangGraph
as the outer state machine with PydanticAI agents as stateless nodes, but this is not
made explicit anywhere in code or docs. The failure mode is two loop-management systems
fighting each other — PydanticAI retrying internally while LangGraph is also routing
retries externally.

**The architectural call that must be made explicit:**

> LangGraph is the workflow orchestrator. PydanticAI agents are stateless callables —
> they receive a prompt, return a typed model, and exit. They do NOT manage state across
> calls. LangGraph owns all state (via `RalphState`). PydanticAI owns all structured
> output parsing and model interaction.

This should be codified in `ARCHITECTURE.md` and in each worker's module docstring.

**Specific risk in the current code:**
`agents/workers/validator.py` calls `run_lint.fn()` and `run_tests.fn()` directly
(as plain functions, bypassing the `@tool` decorator machinery). This is correct for
v1, but creates confusion about when tools are "agent tools" vs. "utility functions."
Clarify the pattern.

**Files to update:**
- `ARCHITECTURE.md` — add explicit "Integration Model" section
- `agents/workers/*.py` — add module-level docstring stating the node/callable contract

---

### 3. Gemini Structured Output Reliability

**The issue:**
The entire pipeline assumes the model returns valid Pydantic-conforming JSON on every
call. Gemini Flash's instruction following is strong but not perfect, especially on
complex nested models like `PlanOutput` with `list[ExecutionStep]`. A single malformed
response breaks the entire LangGraph run.

**PydanticAI supports this natively** via the `retries=` parameter on `Agent()`.
When validation fails, PydanticAI feeds the validation error back to the model and
asks it to correct the output. This retry loop must be configured before the LangGraph
layer ever sees a failure — otherwise LangGraph's own retry logic triggers on what is
really a model formatting issue.

**Fix:**
```python
# In every worker, change:
_agent = Agent(model=get_model(), result_type=PlanOutput, system_prompt=SYSTEM_PROMPT)

# To:
_agent = Agent(
    model=get_model(),
    result_type=PlanOutput,
    system_prompt=SYSTEM_PROMPT,
    retries=3,  # PydanticAI-level retry with validation error feedback
)
```

**Files to touch:**
- `agents/workers/planner.py`
- `agents/workers/implementer.py`
- `agents/workers/reviewer.py`
- `agents/workers/validator.py`
- `agents/workers/cleaner.py`

---

### 4. Browser Tools Are the Weakest Link

**The issue:**
`drive_ui_flow(url, steps: list[UIAction])` hides enormous complexity. Playwright
selectors go stale on re-renders, SPAs need explicit wait strategies, auth state needs
management across steps, and headless browser stability varies by environment.

This is Phase 6 work. If it sits on the critical path of `ralph_loop.py`'s validation,
it stalls the entire system until it's solid.

**Fix:**
Make browser validation **optional** — a capability the planner may invoke, not a
mandatory node. In the Ralph Loop:
- Browser tools are only included in `available_tools` when the task involves UI changes
  (detected by planner from keywords: "page", "UI", "frontend", "endpoint", "renders")
- The planner sets a `requires_browser_validation: bool` field in `PlanOutput` (add
  this field)
- `ralph_loop.py` only inserts the `ui_validate_node` when this flag is true

This ensures the entire non-UI workflow path ships and is stable before the browser
path is hardened.

**Files to touch:**
- `agents/models/planner.py` — add `requires_browser_validation: bool = False`
- `agents/workflows/ralph_loop.py` — make `ui_validate_node` conditional
- `agents/tools/registry.py` — only surface browser tools when relevant

---

### 5. Cost Model Is an Output Metric, Not an Input Constraint

**The issue:**
`RunMetrics` tracks cost after the fact (correct), but `RalphState` has no cost ceiling.
A task hitting `MAX_IMPLEMENT_ITERATIONS=5` with a complex `PlanOutput` and large context
could run $5–15 on Gemini Flash in dev. Without a budget constraint, the system will
overspend in early testing before iteration patterns are calibrated.

**Fix:**
Add `cost_budget_usd: float` to `RalphState` and check it in `check_guards()`:

```python
# In agents/core/guards.py:
MAX_COST_USD_PER_RUN = 2.00  # dev default; raise for production tasks

def check_guards(state: RalphState) -> GuardResult:
    ...
    if state.get("estimated_cost_usd", 0.0) >= state.get("cost_budget_usd", MAX_COST_USD_PER_RUN):
        return GuardResult(
            allowed=False,
            reason=f"Cost budget ${state['cost_budget_usd']:.2f} reached",
            action="escalate",
        )
```

Token counts from PydanticAI's `RunResult.usage()` should be accumulated into
`RalphState["estimated_cost_usd"]` after each node.

**Files to touch:**
- `agents/core/guards.py` — add cost guard + `MAX_COST_USD_PER_RUN` constant
- `agents/core/state.py` — add `estimated_cost_usd: float` and `cost_budget_usd: float`
- `agents/workflows/ralph_loop.py` — accumulate token costs from each `RunResult`

---

### 6. Reviewer Agent Has Correlated Blind Spots

**The issue:**
An agent reviewing its own sibling agent's work within the same model family has
correlated blind spots. The reviewer will tend to approve things the implementer
generated because they share the same underlying priors. This is a well-documented
failure mode in multi-agent systems.

**Two concrete fixes:**

**(a) Adversarial reviewer framing** — change the reviewer's system prompt to assume
the implementation is wrong until proven otherwise:

```
# Current framing:
"Your job is to review a pull request and produce a structured review."

# Adversarial framing:
"Your job is to find problems in this implementation. Assume there are bugs,
architecture violations, or edge cases the implementer missed. Approve only if
you cannot find any blocking issues after thorough scrutiny."
```

**(b) Hard pre-check before the agent runs** — run `arch_lint` and `golden_lint` as
a deterministic gate before `review_loop_node`. If structural checks fail, the diff
never reaches the reviewer. The agent only reviews code that already passed the
machine-checkable rules, so it can focus on logic, correctness, and intent.

Approach (b) is lower effort and higher reliability. It also means lint violations
never appear in `ReviewOutput.arch_violations` — they're caught earlier.

**Files to touch:**
- `agents/workers/reviewer.py` — update `SYSTEM_PROMPT` with adversarial framing
- `agents/workflows/ralph_loop.py` — add lint pre-check node before `review_loop_node`

---

## Minor Things

### QUALITY_SCORE.md Trust Problem
`QUALITY_SCORE.md` is auto-updated by the agent but also serves as ground truth for
humans. A bug in the GC workflow could silently produce optimistic scores. Humans
currently see only the current state — no delta, no history.

**Fix:** Commit `QUALITY_SCORE.md` changes as a dated entry appended to a
`docs/quality-history/YYYY-MM-DD.md` file (or use git log as the audit trail, since
the file is version-controlled). At minimum, make CI fail if the score regresses more
than 1.0 point between commits without a corresponding PR that justifies it.

---

### Worktree Port Coordination at Scale
`worktree_up.sh` allocating unique port ranges (base + offset) works for 2–3 parallel
runs but becomes a coordination problem at 10+. Two scripts running in parallel with
the same offset will collide.

**Fix (when needed):** Use a lock file at `~/.ouroboros/ports.lock` and a port registry
at `~/.ouroboros/port-assignments.json`. `worktree_up.sh` atomically claims the next
available offset. Fine to defer until parallelism becomes real.

---

### Verification Plan Is Solid
The 13-step verification plan in `FULL-PLAN.md` is explicit and runnable. Most
production systems don't have this. Keep it — and add each check as a script in
`scripts/verify/` so they can be run non-interactively in CI.
