# AGENTS.md — Project Ouroboros Agent Entry Point

> This file is the primary entry point for all agent runs. Read this first.
> It defines the operating model, key locations, and decision rules.

---

## What Is This System?

Project Ouroboros is an agent-first software factory. Agents plan, implement, review, validate,
and merge code autonomously. Humans define tasks and review escalations.

The system is self-referential: agents can improve the agent infrastructure itself.

---

## Core Operating Principles

1. **Structured outputs only** — All agent outputs are typed Pydantic models. No text parsing.
2. **Token budget discipline** — Use `build_context()`, never read the whole repo.
3. **Guard rails are hard limits** — `MAX_IMPLEMENT_ITERATIONS = 5`. Never bypass.
4. **Tools from registry only** — Never hallucinate tool names. Query `REGISTRY.all_tools()`.
5. **Entropy is a first-class concern** — The GC workflow runs daily. Keep it green.
6. **Cost awareness** — Every run emits `RunMetrics`. Track cost regression.

---

## Navigation Map

### Architecture & Design
- `ARCHITECTURE.md` — Domain/layer map with dependency rules
- `docs/DESIGN.md` — System design overview
- `docs/GOLDEN_PRINCIPLES.md` — Machine-checkable GP-001 through GP-010
- `docs/QUALITY_SCORE.md` — Per-domain quality grades (auto-updated by GC)
- `docs/design-docs/core-beliefs.md` — Agent-first operating principles
- `docs/PLANS.md` — How to read and write execution plans

### Execution Plans
- `docs/exec-plans/active/` — In-progress plans (versioned, updated every 7 days)
- `docs/exec-plans/completed/` — Archived plans (never deleted)

### Agent Code
- `agents/core/config.py` — Vertex AI + model configuration
- `agents/core/state.py` — LangGraph typed state schema
- `agents/core/guards.py` — Hard limits (iteration + tool-call guards)
- `agents/core/context_builder.py` — `build_context(task)` → scoped token budget

### Agent Workers (PydanticAI)
- `agents/workers/planner.py` — Decomposes task into typed steps
- `agents/workers/implementer.py` — Writes code, returns `FileChange[]`
- `agents/workers/reviewer.py` — Reviews diff, returns `ReviewOutput`
- `agents/workers/validator.py` — Runs tests/lint, returns `ValidationOutput`
- `agents/workers/cleaner.py` — Detects entropy, returns `CleanupOutput`

### Typed Output Models
- `agents/models/planner.py` — `PlanOutput`, `ExecutionStep`
- `agents/models/implementer.py` — `ImplementOutput`, `FileChange`
- `agents/models/reviewer.py` — `ReviewOutput`, `ReviewComment`
- `agents/models/validator.py` — `ValidationOutput`, `TestResult`, `LintResult`
- `agents/models/cleaner.py` — `CleanupOutput`, `EntropyViolation`
- `agents/models/cost.py` — `CostSummary`, `RunMetrics`

### Tools
- `agents/tools/registry.py` — `ToolRegistry` — capability catalog
- `agents/tools/fs.py` — File system tools
- `agents/tools/shell.py` — Test/lint/build runners
- `agents/tools/git.py` — Git + GitHub PR tools
- `agents/tools/browser.py` — Playwright browser automation
- `agents/tools/observability.py` — LogQL + PromQL query tools

### Workflows (LangGraph)
- `agents/workflows/ralph_loop.py` — Main PR lifecycle workflow
- `agents/workflows/reviewer_loop.py` — Agent-to-agent review workflow
- `agents/workflows/entropy_gc.py` — Entropy scanning + cleanup PR workflow

### Repo Index
- `repo_index/build_index.py` — Generates `symbols.json` + `file_map.json`
- `repo_index/symbols.json` — Symbol → file + line
- `repo_index/file_map.json` — file → domain, layer, imports, exports

### Linting
- `lint/arch_lint.py` — Layer dependency checker (REMEDIATION messages)
- `lint/golden_lint.py` — GP-001 through GP-010 enforcement
- `lint/doc_lint.py` — Stale doc detection
- `lint/rules.py` — Named rules with `AGENT_REMEDIATION` fields
- `lint/run_lint.py` — CLI runner

### Tests
- `tests/agent_eval/test_bug_fix.py` — Agent fixes buggy code
- `tests/agent_eval/test_feature_gen.py` — Agent generates feature
- `tests/agent_eval/test_entropy_gc.py` — GC detects and cleans violations

### Harness
- `harness/observability/docker-compose.yml` — VictoriaLogs + VictoriaMetrics + Grafana
- `harness/sandbox/docker-compose.yml` — Per-worktree app isolation
- `scripts/worktree_up.sh` / `worktree_down.sh` — Worktree lifecycle

---

## Starting a Task

1. Read this file (done)
2. Read `ARCHITECTURE.md` for layer rules
3. Call `build_context(task)` to get your scoped context package
4. Check `REGISTRY.all_tools()` for available tools
5. Check `docs/exec-plans/active/` for any active plan for this domain
6. Start the appropriate workflow in `agents/workflows/`

## Guard Rails — NEVER Bypass

```
MAX_IMPLEMENT_ITERATIONS = 5
MAX_REVIEW_ITERATIONS = 3
MAX_TOOL_CALLS_PER_NODE = 50
MAX_TOTAL_TOOL_CALLS = 200
```

When limits are hit → escalate to human checkpoint. Do not retry.

---

## Key Invariants

- Workers NEVER cross-import. Shared logic lives in `agents/core/` or `agents/models/`.
- All external data is validated at boundaries (Pydantic models).
- No `print()` outside `scripts/`. Use structured logging.
- No file exceeds 500 lines (GP-002).
- All tool functions are in `agents/tools/` and registered in `ToolRegistry`.
