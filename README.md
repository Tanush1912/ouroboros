<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python 3.12+"/>
  <img src="https://img.shields.io/badge/model-Gemini_3.0_Flash-4285F4?logo=google&logoColor=white" alt="Gemini 3.0 Flash"/>
  <img src="https://img.shields.io/badge/framework-PydanticAI-E92063?logo=pydantic&logoColor=white" alt="PydanticAI"/>
  <img src="https://img.shields.io/badge/orchestration-LangGraph-1C3C3C" alt="LangGraph"/>
  <img src="https://img.shields.io/badge/tracing-Logfire-FF6B35" alt="Logfire"/>
  <img src="https://img.shields.io/badge/package_manager-uv-DE5FE9" alt="uv"/>
  <img src="https://img.shields.io/badge/tests-46_passing-brightgreen" alt="Tests"/>
</p>

<h1 align="center">Ouroboros</h1>
<h3 align="center">AI Agent Software Development Infrastructure</h3>

<p align="center">
  <em>The system that manages and improves itself.</em>
</p>

---

**Ouroboros** is an agent-first software factory. It takes a natural language task as input and produces a merged, tested, reviewed pull request as output. Five specialized AI agents — planner, implementer, reviewer, validator, and cleaner — collaborate through typed contracts to autonomously write code, run tests, open PRs, review changes, and merge them.

The system is self-referential: agents can be tasked to improve the agent infrastructure itself — better prompts, tighter lint rules, new tools — all flowing through the same PR review process.

```
"Fix the off-by-one error in utils/counter.py"
         │
         ▼
┌──────────────────────────────────────────────────────────────┐
│                      OUROBOROS                                │
│                                                              │
│   Plan ──▶ Implement ──▶ Validate ──▶ Open PR ──▶ Review    │
│                 ▲              │                      │       │
│                 └──── retry ◀──┘                      │       │
│                                              approved?│       │
│                                         yes ──▶ Merge │       │
│                                         no  ──▶ Fix   │       │
└──────────────────────────────────────────────────────────────┘
         │
         ▼
   Merged PR #42 ✓
```

---

## Table of Contents

- [Why Ouroboros?](#why-ouroboros)
- [Architecture Overview](#architecture-overview)
- [The Ralph Loop — PR Lifecycle Workflow](#the-ralph-loop--pr-lifecycle-workflow)
- [Agent Workers](#agent-workers)
- [Typed Output Models](#typed-output-models)
- [Tool System](#tool-system)
- [Guard Rails](#guard-rails)
- [Cost Awareness](#cost-awareness)
- [Entropy Management & Garbage Collection](#entropy-management--garbage-collection)
- [Repository Index](#repository-index)
- [Context Builder](#context-builder)
- [Lint Framework](#lint-framework)
- [Observability](#observability)
- [Infrastructure & Sandboxing](#infrastructure--sandboxing)
- [Test Suite](#test-suite)
- [Core Beliefs](#core-beliefs)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [CI/CD Pipelines](#cicd-pipelines)

---

## Why Ouroboros?

Traditional software development is a loop: **plan → write → test → review → merge → repeat**. Ouroboros encodes this loop as a state machine where AI agents execute each step, with typed contracts at every boundary and hard limits to prevent runaway execution.

**Key design constraints:**

1. **No text parsing, ever.** Every agent output is a typed Pydantic model. No regex, no JSON extraction, no "parse the LLM response." If a handoff can fail silently, it will — so every handoff is a type.

2. **Guards are hard limits, not suggestions.** `MAX_IMPLEMENT_ITERATIONS = 5` is a constant, not a config value. An agent that loops forever is worse than one that escalates to a human.

3. **Token budgets are first-class.** The context builder enforces a token budget before agents see anything. Agents that read the whole repo are agents that fail on large repos.

4. **Entropy is tracked daily.** Ten machine-checkable Golden Principles (GP-001 to GP-010) are enforced by linters and a daily garbage collection workflow that opens atomic cleanup PRs.

5. **Self-improvement is the point.** Agents can write better agent workers, tighter lint rules, and new tools — all flowing through the same PR review process as any other change.

---

## Architecture Overview

Ouroboros uses a strict layered architecture enforced by AST-based linting. Each layer can only import from layers below it:

```
                    ┌─────────────────────┐
                    │     WORKFLOWS       │  LangGraph state machines
                    │  ralph_loop.py      │  (entry points)
                    │  entropy_gc.py      │
                    │  reviewer_loop.py   │
                    └────────┬────────────┘
                             │ imports ▼
                    ┌─────────────────────┐
                    │      WORKERS        │  PydanticAI agents
                    │  planner.py         │  (one per role)
                    │  implementer.py     │
                    │  reviewer.py        │
                    │  validator.py       │
                    │  cleaner.py         │
                    └────────┬────────────┘
                             │ imports ▼
                    ┌─────────────────────┐
                    │       TOOLS         │  @tool functions
                    │  fs.py  shell.py    │  + ToolRegistry
                    │  git.py browser.py  │
                    │  observability.py   │
                    └────────┬────────────┘
                             │ imports ▼
                    ┌─────────────────────┐
                    │       CORE          │  Guards, state, context
                    │  guards.py          │  builder, instrumentation
                    │  state.py           │
                    │  context_builder.py │
                    │  config.py          │
                    └────────┬────────────┘
                             │ imports ▼
                    ┌─────────────────────┐
                    │      MODELS         │  Pure Pydantic types
                    │  PlanOutput         │  (zero dependencies)
                    │  ImplementOutput    │
                    │  ReviewOutput       │
                    │  ValidationOutput   │
                    │  CleanupOutput      │
                    │  CostSummary        │
                    └─────────────────────┘
```

**Enforced invariants:**
- Workers **cannot** cross-import each other (shared logic goes to `core/` or `models/`)
- Tools **cannot** import workers (tools are stateless; workers orchestrate them)
- Models **cannot** import anything above them (pure types, zero side effects)

Violations are caught by `lint/arch_lint.py` with actionable `AGENT_REMEDIATION` messages so agents can self-fix.

---

## The Ralph Loop — PR Lifecycle Workflow

The Ralph Loop (`agents/workflows/ralph_loop.py`) is the main workflow. It takes a task string and produces a merged PR:

```
                              ┌─────────┐
                              │  START  │
                              └────┬────┘
                                   │
                                   ▼
                           ┌───────────────┐
                           │   plan_node   │ ← PlannerAgent
                           │               │   → PlanOutput
                           └───────┬───────┘
                                   │
                                   ▼
                        ┌────────────────────┐
                   ┌───▶│  implement_node    │ ← ImplementerAgent
                   │    │                    │   → ImplementOutput
                   │    │  writes files      │   → FileChange[]
                   │    └────────┬───────────┘
                   │             │
                   │             ▼
                   │    ┌────────────────────┐
                   │    │  validate_node     │ ← ValidatorWorker (deterministic)
                   │    │                    │   runs pytest + ruff + arch_lint
                   │    │  → ValidationOutput│
                   │    └────────┬───────────┘
                   │             │
                   │             ▼
                   │    ┌────────────────────┐
                   │    │  route decision    │
                   │    └──┬──────┬──────┬───┘
                   │       │      │      │
                   │  retry │  proceed  escalate
                   │  (max 5)│      │      │
                   └───────┘      │      ▼
                                  │  ┌──────────────────┐
                                  │  │ human_checkpoint  │
                                  │  └──────────────────┘
                                  ▼
                        ┌────────────────────┐
                        │  ui_validate_node  │ ← Optional: Playwright screenshots
                        └────────┬───────────┘
                                 │
                                 ▼
                        ┌────────────────────┐
                        │   open_pr_node     │ ← git commit + gh pr create
                        └────────┬───────────┘
                                 │
                                 ▼
                        ┌────────────────────┐
                   ┌───▶│ review_loop_node   │ ← ReviewerAgent
                   │    │                    │   → ReviewOutput
                   │    └────────┬───────────┘
                   │             │
                   │    ┌────────┴───────────┐
                   │    │  approved?          │
                   │    └──┬──────────────┬──┘
                   │       │              │
                   │   no (max 3)     yes │
                   └───────┘              ▼
                                ┌──────────────────┐
                                │   merge_node     │ ← gh pr merge --squash
                                └────────┬─────────┘
                                         │
                                         ▼
                                    ┌─────────┐
                                    │  DONE   │
                                    └─────────┘
```

**Conditional routing** is driven entirely by typed model fields — no string matching:
- `ValidationOutput.next_action`: `"proceed"` | `"retry"` | `"escalate"`
- `ReviewOutput.approved`: `true` → merge, `false` → address feedback

**Entry point:**
```python
result = await run_ralph_loop("Fix the off-by-one error in utils/counter.py")
# result.status == "done"
# result.pr_url == "https://github.com/org/repo/pull/42"
# result.estimated_cost_usd == 0.012
```

---

## Agent Workers

Five specialized workers, each returning typed Pydantic models:

| Worker | Input | Output | Uses LLM? |
|--------|-------|--------|-----------|
| **Planner** | Task + TaskContext | `PlanOutput` (steps, risk, domains) | Yes |
| **Implementer** | Task + Plan + prior failures | `ImplementOutput` (FileChange[], commit msg) | Yes |
| **Reviewer** | PR diff + task context | `ReviewOutput` (approved, comments, blocking issues) | Yes |
| **Validator** | (runs tools directly) | `ValidationOutput` (test/lint results, next_action) | **No** |
| **Cleaner** | Scan report + domains | `CleanupOutput` (violations, quality scores, PR recs) | Yes |

**The Validator is deliberately deterministic** — it runs `pytest` and lint tools, then calls a pure function (`determine_next_action()`) to decide the next step. No LLM call, no ambiguity.

Each LLM-based worker:
- Loads a system prompt from `agents/prompts/*.txt`
- Uses `get_model()` (Gemini 3.0 Flash via Vertex AI)
- Returns `(TypedOutput, TokenUsage)` for cost tracking
- Has `retries=3` for transient failures

---

## Typed Output Models

Every agent-to-agent handoff is a Pydantic model. Here are the key types:

```python
# Planning
class ExecutionStep(BaseModel):
    description: str
    files_affected: list[str]
    tool: Literal["fs", "shell", "git", "browser", "observability", "index"]
    expected_output: str

class PlanOutput(BaseModel):
    task_summary: str
    steps: list[ExecutionStep]
    risk_level: Literal["low", "medium", "high"]
    requires_human_review: bool
    requires_browser_validation: bool
    affected_domains: list[str]

# Implementation
class FileChange(BaseModel):
    path: str
    operation: Literal["create", "modify", "delete"]
    content: str | None
    diff_summary: str

class ImplementOutput(BaseModel):
    files_changed: list[FileChange]
    commit_message: str
    test_commands: list[str]

# Validation (drives routing)
class ValidationOutput(BaseModel):
    tests: TestResult
    lint: LintResult
    arch_lint: LintResult
    overall_pass: bool
    next_action: Literal["proceed", "retry", "escalate"]  # ← routing signal
    failure_summary: str

# Review (drives merge decision)
class ReviewOutput(BaseModel):
    approved: bool  # ← merge gate
    comments: list[ReviewComment]
    blocking_issues: list[str]
    summary: str
    arch_violations: list[str]
```

The `next_action` and `approved` fields are what drive LangGraph's conditional edges. Pure type routing — no string parsing.

---

## Tool System

All agent capabilities are registered in a `ToolRegistry` singleton. The planner queries `REGISTRY.all_tools()` before creating a plan, ensuring it can only reference tools that actually exist.

### Tool Catalog

| Category | Tool | Description |
|----------|------|-------------|
| **fs** | `read_file(path)` | Read a file from the repo |
| | `write_file(path, content)` | Write content, create parent dirs |
| | `list_dir(path)` | List directory contents |
| | `search_repo(query, pattern)` | Ripgrep search across repo |
| | `search_symbol(name)` | O(1) lookup in repo index |
| | `reindex(paths)` | Update symbol index for changed files |
| **shell** | `run_tests(path)` | Run pytest, return structured `TestResult` |
| | `run_lint(path)` | Run ruff + arch_lint + golden_lint |
| | `run_build()` | Build the application |
| | `run_command(cmd)` | Run arbitrary shell command |
| **git** | `git_status()` | Branch, changed, staged, untracked files |
| | `commit(message, files)` | Stage specific files and commit |
| | `open_pr(title, body)` | Create PR via `gh` CLI |
| | `get_pr_diff(pr_number)` | Fetch PR diff |
| | `get_pr_comments(pr_number)` | Fetch review comments |
| | `merge_pr(pr_number, strategy)` | Merge PR (squash/merge) |
| **browser** | `take_screenshot(url)` | Playwright screenshot (base64 PNG) |
| | `snapshot_dom(url)` | Capture accessibility tree |
| | `drive_ui_flow(url, steps)` | Execute UI action sequence |
| **observability** | `query_logs(logql)` | Query VictoriaLogs (LogQL syntax) |
| | `query_metrics(promql)` | Query VictoriaMetrics (PromQL syntax) |

Every tool returns a **typed Pydantic model** — `TestResult`, `CommitResult`, `PRResult`, `ScreenshotResult`, etc. No raw strings.

```python
# Tool capability metadata — used by planner to understand what's available
class ToolCapability(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_type: str
    category: Literal["fs", "shell", "git", "browser", "observability", "index"]
    requires_sandbox: bool
```

---

## Guard Rails

Hard limits enforced at the entry of every LangGraph node via `pre_node_guard()`. These are **constants, not config** — intentionally not tunable at runtime:

```
┌──────────────────────────────────────────────────────────────┐
│                     GUARD RAILS                              │
│                                                              │
│   MAX_IMPLEMENT_ITERATIONS  = 5     implement→validate loops │
│   MAX_REVIEW_ITERATIONS     = 3     review→fix loops         │
│   MAX_TOOL_CALLS_PER_NODE   = 50    tools per LangGraph node │
│   MAX_TOTAL_TOOL_CALLS      = 200   tools across entire run  │
│   MAX_COST_USD_PER_RUN      = $2.00 cost ceiling per workflow│
│                                                              │
│   Exceeded? ──▶ "escalate" (human checkpoint)                │
│   Tool budget exhausted? ──▶ "abort" (fail cleanly)          │
└──────────────────────────────────────────────────────────────┘
```

```python
def check_guards(state: RalphState) -> GuardResult:
    """Checked at every node entry. Returns allowed/escalate/abort."""
    if state.iteration_count >= MAX_IMPLEMENT_ITERATIONS:
        return GuardResult(allowed=False, action="escalate")
    if state.estimated_cost_usd >= state.cost_budget_usd:
        return GuardResult(allowed=False, action="escalate")
    ...
```

When an agent can't solve a problem within bounds, it **escalates to a human** rather than burning tokens indefinitely.

---

## Cost Awareness

Every workflow run tracks token usage and cost, producing a `RunMetrics` report:

```python
class TokenUsage(BaseModel):
    tokens_in: int
    tokens_out: int

    def cost_usd(self) -> float:
        """Gemini 3.0 Flash: $0.25/1M input, $1.50/1M output"""
        return (self.tokens_in * 0.25 + self.tokens_out * 1.50) / 1_000_000

class RunMetrics(BaseModel):
    cost: CostSummary
    per_node_costs: dict[str, CostSummary]  # Cost per LangGraph node
    highest_cost_node: str                   # Where most tokens were spent
```

```
Example run breakdown:
┌─────────────────┬──────────┬───────────┬──────────┐
│ Node            │ Input Tk │ Output Tk │ Cost USD │
├─────────────────┼──────────┼───────────┼──────────┤
│ plan_node       │   2,100  │     800   │  $0.0017 │
│ implement_node  │   4,500  │   2,200   │  $0.0044 │
│ validate_node   │       0  │       0   │  $0.0000 │
│ review_node     │   3,800  │   1,100   │  $0.0026 │
├─────────────────┼──────────┼───────────┼──────────┤
│ TOTAL           │  10,400  │   4,100   │  $0.0087 │
└─────────────────┴──────────┴───────────┴──────────┘
```

Cost data flows to Logfire, building a dataset of cost-per-PR-by-task-type for regression tracking.

---

## Entropy Management & Garbage Collection

Entropy is tracked as a first-class concern through ten **Golden Principles** — machine-checkable rules enforced by `lint/golden_lint.py` and a daily GC workflow:

| Principle | Rule | Severity | Auto-fixable |
|-----------|------|----------|-------------|
| **GP-001** | No duplicate utility functions across packages | error | Yes |
| **GP-002** | No file exceeds 500 lines | warning | No |
| **GP-003** | No hand-rolled helpers duplicating shared packages | warning | No |
| **GP-004** | All external data validated at boundary (Pydantic) | error | No |
| **GP-005** | No `print()` outside `scripts/` — use structured logging | info | Yes |
| **GP-006** | Schema types follow `*Output`/`*Result`/`*Schema` naming | info | No |
| **GP-007** | No dead imports | info | Yes |
| **GP-008** | All docs reference real code that still exists | warning | No |
| **GP-009** | Active exec-plans updated within 7 days | warning | No |
| **GP-010** | `QUALITY_SCORE.md` regenerated within 24 hours | info | Yes |

### Entropy GC Workflow

The entropy GC workflow (`agents/workflows/entropy_gc.py`) runs daily via GitHub Actions:

```
┌────────────────────┐
│  entropy_scan_node │ ← Run all linters, collect violations
└────────┬───────────┘
         │
         ▼
┌────────────────────────┐
│ analyze_violations_node│ ← CleanerAgent clusters violations
└────────┬───────────────┘   by principle + domain
         │
         ▼
┌────────────────────────┐
│ open_cleanup_prs_node  │ ← One atomic PR per violation cluster
│                        │   "[gc] GP-001: remove duplicate
│                        │    logging utilities in billing/"
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│update_quality_score_node│ ← Write docs/QUALITY_SCORE.md
└────────────────────────┘
```

Each cleanup PR is:
- **Atomic** — one principle violation cluster per PR
- **Auto-mergeable** — if tests pass, no human required
- **Tiny** — <1 minute review time

---

## Repository Index

The repo index (`repo_index/`) provides O(1) symbol lookup so agents don't need to read every file:

```python
# Instead of reading 50 files to find a class:
@tool
def search_symbol(name: str) -> SymbolLocation | None:
    """Look up a symbol by name. Returns file + line."""
    # O(1) lookup in symbols.json
```

**Generated files:**
- `symbols.json` — Symbol name to file + line + kind (class, function, constant)
- `file_map.json` — File path to domain, layer, imports, exports

```json
// symbols.json (189 symbols indexed across 47 files)
{
  "ValidationOutput": {"file": "agents/models/validator.py", "line": 42, "kind": "class"},
  "run_planner":      {"file": "agents/workers/planner.py",  "line": 18, "kind": "async_function"}
}

// file_map.json
{
  "agents/workers/planner.py": {
    "domain": "agents",
    "layer": "workers",
    "imports": ["agents.models.planner", "agents.core.config"],
    "exports": ["run_planner"]
  }
}
```

The index is rebuilt automatically on every merge to `main` via CI, and agents can call `reindex()` after writing files.

---

## Context Builder

Agents never receive raw file dumps. The context builder (`agents/core/context_builder.py`) produces a token-budgeted context package:

```
Task: "Fix the login endpoint validation"
                    │
                    ▼
            build_context(task, max_tokens=8000)
                    │
    ┌───────────────┼───────────────────┐
    │               │                   │
    ▼               ▼                   ▼
Query repo     Load arch        Query tool
index for      rules for        registry for
relevant       touched          available
files          layers           capabilities
    │               │                   │
    └───────────────┼───────────────────┘
                    │
                    ▼
            ┌───────────────┐
            │  TaskContext   │
            │               │
            │ relevant_files│ ← trimmed snippets
            │ relevant_docs │ ← ARCHITECTURE.md sections
            │ arch_rules    │ ← active rules for domain
            │ active_plans  │ ← exec-plans in progress
            │ available_tools│ ← from ToolRegistry
            │ token_budget  │ ← remaining budget
            └───────────────┘
```

The context builder is the **gatekeeper for token spend**. Without it, agents read 50 files and burn context on noise. With it, they receive exactly what they need within budget.

---

## Lint Framework

Four complementary linters work together to enforce code quality:

### Architecture Lint (`lint/arch_lint.py`)
AST-based layer dependency checker. Every violation includes an actionable remediation message:

```
ARCH-VIOLATION: agents/workers/planner.py imports from agents/workers/reviewer.py
RULE: Workers cannot cross-import. Extract shared logic to agents/core/.
REMEDIATION: Move shared type X to agents/models/shared.py and import from there.
DOCS: See ARCHITECTURE.md#worker-isolation
```

### Golden Lint (`lint/golden_lint.py`)
Enforces the 10 Golden Principles. Detection methods:
- **GP-001**: AST body comparison (`ast.unparse()`) across all functions
- **GP-002**: Line counting
- **GP-003**: Pattern matching (`while` + `sleep()` = hand-rolled retry)
- **GP-004**: `json.loads()` without `model_validate()` call
- **GP-005**: `print()` call detection outside allowed directories
- **GP-006**: BaseModel subclass suffix validation in `agents/models/`
- **GP-007**: Delegates to `ruff check --select F401`

### Doc Lint (`lint/doc_lint.py`)
Cross-references backtick paths in `.md` files against the repo index, ensuring documentation references real code that still exists.

### Rule Registry (`lint/rules.py`)
Centralized rule definitions with `AGENT_REMEDIATION` fields:
```python
@dataclass
class LintRule:
    id: str                  # "ARCH-001", "GP-005"
    name: str                # "worker-cross-import"
    description: str         # Human-readable
    severity: str            # "error", "warning", "info"
    agent_remediation: str   # Agent reads this to self-fix
    docs_link: str           # Reference to docs
    auto_fixable: bool       # Can agent fix without human?
```

---

## Observability

Two layers of observability — one for the agent system, one for the applications agents build:

```
┌──────────────────────────────────────────────────────────┐
│  AGENT OBSERVABILITY (Logfire)                           │
│                                                          │
│  PydanticAI ──▶ Logfire (auto-instrumented)              │
│  ├─ Model calls (tokens in/out, latency)                 │
│  ├─ Tool calls (inputs/outputs as Pydantic models)       │
│  ├─ LangGraph node transitions                           │
│  └─ RunMetrics (cost per PR, per node)                   │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│  APP OBSERVABILITY (VictoriaLogs + VictoriaMetrics)      │
│                                                          │
│  App ──▶ Vector ──▶ VictoriaLogs (LogQL @ :9428)         │
│                  └──▶ VictoriaMetrics (PromQL @ :8428)   │
│                                                          │
│  Grafana dashboard at :3000                              │
│  Agents query via query_logs() and query_metrics() tools │
└──────────────────────────────────────────────────────────┘
```

Agents can query the observability stack to diagnose issues — the same way humans do:

```python
# Agent querying logs to diagnose an error
logs = await query_logs('{service="api"} |= "error"', duration="1h")

# Agent checking request latency
metrics = await query_metrics('rate(http_requests_total[5m])', duration="1h")
```

---

## Infrastructure & Sandboxing

### Observability Stack (`harness/observability/`)

```yaml
# docker-compose.yml
services:
  vector:              # Log/metric aggregation (port 8686)
  victoria-logs:       # LogQL log storage (port 9428, 7-day retention)
  victoria-metrics:    # PromQL metric storage (port 8428, 7-day retention)
  grafana:             # Dashboard (port 3000)
```

### Per-Worktree Sandbox (`harness/sandbox/`)

Each agent worktree gets an isolated Docker environment:

```bash
# Spin up isolated env for a task
scripts/worktree_up.sh feature-login 8100
# Creates git worktree at ../project-ouroboros-feature-login
# Starts sandbox containers on port 8100+

# Tear down when done
scripts/worktree_down.sh feature-login
```

Worktrees get isolated Docker networks (`ouroboros-{name}`), unique port allocations, and separate Vector instances forwarding to the main observability stack.

---

## Test Suite

46 tests organized into two categories, all runnable without GCP credentials or `pydantic_ai` installed:

### Lint Tests (`tests/lint/`)
| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_arch_lint.py` | 5 | Worker cross-import, tool→worker import, clean files, remediation messages |
| `test_golden_lint.py` | 11 | GP-001 through GP-006 (duplicates, file size, hand-rolled retry, validation, print, naming) |

### Agent Eval Tests (`tests/agent_eval/`)
| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_guards.py` | 6 | All guard types: iteration limits, tool budget, cost ceiling |
| `test_validator_logic.py` | 6 | `determine_next_action()` routing: proceed, retry, escalate |
| `test_bug_fix.py` | 5 | Model contracts for bug-fix workflow (PlanOutput, ImplementOutput, ValidationOutput) |
| `test_feature_gen.py` | 5 | Model contracts for feature generation (plan, implement, review) |
| `test_entropy_gc.py` | 8 | Entropy violation models, cleanup output, quality scoring, clustering |

**Design principle:** Deterministic logic (guards, validator routing, model contracts) is tested without an LLM. Probabilistic behavior (actual agent runs) uses mocks in CI and requires GCP credentials for integration testing.

```bash
# Run all tests
uv run pytest tests/ -v

# Run only lint tests
uv run pytest tests/lint/ -v

# Run only agent eval tests
uv run pytest tests/agent_eval/ -v
```

---

## Core Beliefs

Ten foundational principles that guide every design decision (from `docs/design-docs/core-beliefs.md`):

| # | Belief | Implication |
|---|--------|-------------|
| 1 | **Structure over text** | Pydantic models at every boundary |
| 2 | **Planner is not omniscient** | Must query `REGISTRY.all_tools()` before planning |
| 3 | **Token budget is first-class** | `build_context()` enforces limits |
| 4 | **Guards are not suggestions** | Hard constants, not runtime config |
| 5 | **Repo index is the map** | `search_symbol()` over `read_file()` |
| 6 | **Entropy accumulates** | Daily GC workflow prevents compounding |
| 7 | **Every run has a cost** | `CostSummary` tracks regression |
| 8 | **Self-referential loop is the feature** | Agents improve agents, through PR review |
| 9 | **Observability is a tool** | Agents query `query_logs()` / `query_metrics()` |
| 10 | **Small, atomic, reversible** | 10 small PRs > 1 large PR |

---

## Tech Stack

| Layer | Tool | Why |
|-------|------|-----|
| **Language Model** | Gemini 3.0 Flash via Vertex AI | Production-grade rate limits, IAM auth, regional isolation |
| **Agent Framework** | PydanticAI | Typed structured outputs, native Logfire tracing |
| **Orchestration** | LangGraph | Explicit state machine, conditional routing, human escalation |
| **Tracing** | Logfire | First-class PydanticAI instrumentation, OTel native |
| **Language** | Python 3.12+ | |
| **Package Manager** | uv | Fast, lockfile-based dependency resolution |
| **Linter/Formatter** | ruff | Covers isort + flake8 + pyupgrade + more |
| **Tests** | pytest + pytest-asyncio | Async-native test runner |
| **Git Automation** | gh CLI | Programmatic PR create/review/merge |
| **Browser** | Playwright | DOM snapshots + screenshots for UI validation |
| **Log Storage** | VictoriaLogs | LogQL-compatible, queryable by agents |
| **Metric Storage** | VictoriaMetrics | PromQL-compatible, queryable by agents |
| **Log Routing** | Vector | Routes app logs/metrics to storage |
| **Dashboards** | Grafana | Human-facing visualization |
| **CI** | GitHub Actions | Lint + tests on every PR, entropy GC daily |
| **Build** | hatchling | PEP 517 build backend |

---

## Repository Structure

```
project-ouroboros/
├── AGENTS.md                        # Agent entry point (read first)
├── ARCHITECTURE.md                  # Layer dependency rules
├── README.md                        # This file
│
├── agents/
│   ├── core/
│   │   ├── config.py                # Vertex AI + Gemini model init
│   │   ├── state.py                 # RalphState TypedDict
│   │   ├── guards.py                # Hard iteration/cost limits
│   │   ├── context_builder.py       # build_context() → TaskContext
│   │   ├── paths.py                 # repo_root() utility
│   │   └── instrumentation.py       # Logfire setup
│   │
│   ├── models/                      # Pure Pydantic output types
│   │   ├── planner.py               # PlanOutput, ExecutionStep
│   │   ├── implementer.py           # ImplementOutput, FileChange
│   │   ├── reviewer.py              # ReviewOutput, ReviewComment
│   │   ├── validator.py             # ValidationOutput, TestResult, LintResult
│   │   ├── cleaner.py               # CleanupOutput, EntropyViolation
│   │   ├── cost.py                  # TokenUsage, CostSummary, RunMetrics
│   │   └── registry.py              # ToolCapability, ToolRegistry
│   │
│   ├── workers/                     # PydanticAI agent implementations
│   │   ├── planner.py               # run_planner() → (PlanOutput, TokenUsage)
│   │   ├── implementer.py           # run_implementer() → (ImplementOutput, TokenUsage)
│   │   ├── reviewer.py              # run_reviewer() → (ReviewOutput, TokenUsage)
│   │   ├── validator.py             # run_validator() → ValidationOutput (no LLM)
│   │   └── cleaner.py               # run_cleaner() → (CleanupOutput, TokenUsage)
│   │
│   ├── tools/                       # @tool functions + registry
│   │   ├── registry.py              # REGISTRY singleton, all tools registered
│   │   ├── fs.py                    # read_file, write_file, search_symbol
│   │   ├── shell.py                 # run_tests, run_lint, run_build
│   │   ├── git.py                   # git_status, commit, open_pr, merge_pr
│   │   ├── browser.py               # take_screenshot, snapshot_dom
│   │   └── observability.py         # query_logs, query_metrics
│   │
│   ├── workflows/                   # LangGraph state machines
│   │   ├── ralph_loop.py            # Main PR lifecycle workflow
│   │   ├── reviewer_loop.py         # Agent-to-agent review
│   │   └── entropy_gc.py            # Daily entropy scan + cleanup PRs
│   │
│   └── prompts/                     # System prompt .txt files
│       ├── planner.txt
│       ├── implementer.txt
│       ├── reviewer.txt
│       └── cleaner.txt
│
├── lint/
│   ├── arch_lint.py                 # AST-based layer dependency checker
│   ├── golden_lint.py               # GP-001 through GP-010 enforcement
│   ├── doc_lint.py                  # Stale doc reference detection
│   ├── rules.py                     # Named rules with AGENT_REMEDIATION
│   └── run_lint.py                  # CLI runner
│
├── repo_index/
│   ├── build_index.py               # Generates symbols.json + file_map.json
│   ├── symbols.json                 # Symbol → file + line + kind
│   └── file_map.json                # File → domain, layer, imports, exports
│
├── tests/
│   ├── lint/                        # Linter unit tests
│   │   ├── test_arch_lint.py
│   │   └── test_golden_lint.py
│   └── agent_eval/                  # Agent behavior tests
│       ├── test_guards.py
│       ├── test_validator_logic.py
│       ├── test_bug_fix.py
│       ├── test_feature_gen.py
│       └── test_entropy_gc.py
│
├── harness/
│   ├── observability/
│   │   └── docker-compose.yml       # VictoriaLogs + VictoriaMetrics + Grafana
│   └── sandbox/
│       └── docker-compose.yml       # Per-worktree app isolation
│
├── scripts/
│   ├── worktree_up.sh               # Spin up isolated worktree env
│   └── worktree_down.sh             # Tear down worktree + containers
│
├── docs/
│   ├── DESIGN.md                    # System design decisions
│   ├── GOLDEN_PRINCIPLES.md         # GP-001 through GP-010
│   ├── QUALITY_SCORE.md             # Auto-updated domain quality grades
│   ├── PLANS.md                     # How to read/write exec plans
│   └── design-docs/
│       └── core-beliefs.md          # 10 foundational principles
│
├── .github/workflows/
│   ├── ci.yml                       # Lint + tests on every PR
│   └── entropy_gc.yml               # Daily entropy scan (6am UTC)
│
└── pyproject.toml                   # uv + ruff + pytest config
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (package manager)
- [gh](https://cli.github.com/) (GitHub CLI, for PR operations)
- Docker + Docker Compose (for observability stack)
- Google Cloud project with Vertex AI enabled (for real agent runs)

### Installation

```bash
# Clone the repository
git clone https://github.com/Tanush1912/project-ouroboros.git
cd project-ouroboros

# Install all dependencies
uv sync --all-extras

# Build the repo index
uv run python repo_index/build_index.py

# Run tests to verify everything works
uv run pytest tests/ -v
```

### Running the Agent System

```bash
# Set required environment variables
export GCP_PROJECT="your-gcp-project-id"
export GCP_LOCATION="us-central1"        # optional, default
export LOGFIRE_TOKEN="your-logfire-token" # optional, for tracing

# Run a task through the Ralph Loop
uv run python -c "
import asyncio
from agents.workflows.ralph_loop import run_ralph_loop
result = asyncio.run(run_ralph_loop('Add a /health endpoint that returns 200'))
print(f'Status: {result[\"status\"]}')
print(f'PR: {result[\"pr_url\"]}')
print(f'Cost: \${result[\"estimated_cost_usd\"]:.4f}')
"
```

### Running the Observability Stack

```bash
# Start the monitoring stack
cd harness/observability
docker compose up -d

# Grafana at http://localhost:3000 (admin/admin)
# VictoriaLogs API at http://localhost:9428
# VictoriaMetrics API at http://localhost:8428
```

### Running Linters

```bash
# Run all linters
uv run python lint/run_lint.py .

# Architecture lint only
uv run python lint/run_lint.py --arch-only .

# Golden principles lint only
uv run python lint/run_lint.py --golden-only .

# Ruff
uv run ruff check .
uv run ruff format --check .
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT` | Yes (for agent runs) | — | Google Cloud project ID |
| `GCP_LOCATION` | No | `us-central1` | Vertex AI region |
| `OUROBOROS_MODEL` | No | `gemini-3.0-flash-preview` | Model name |
| `LOGFIRE_TOKEN` | No | — | Logfire API token for tracing |
| `GITHUB_TOKEN` | No | — | GitHub CLI auth (for PR operations) |
| `VICTORIA_LOGS_URL` | No | `http://localhost:9428` | VictoriaLogs endpoint |
| `VICTORIA_METRICS_URL` | No | `http://localhost:8428` | VictoriaMetrics endpoint |
| `APP_URL` | No | — | Application URL for browser validation |

### Key Configuration Files

| File | Purpose |
|------|---------|
| `pyproject.toml` | Dependencies, ruff config, pytest config |
| `agents/prompts/*.txt` | System prompts (edit to tune agent behavior) |
| `docs/GOLDEN_PRINCIPLES.md` | Quality rules (add new principles here) |
| `lint/rules.py` | Rule definitions with remediation messages |

---

## CI/CD Pipelines

### On Every PR (`ci.yml`)

```
Lint Job                          Test Job
├── ruff check                    ├── Build repo index
├── ruff format --check           ├── Run lint tests (5 + 11)
├── Architecture lint             └── Run agent eval tests (6 + 6 + 5 + 5 + 8)
└── Golden lint                       (with mocked GCP credentials)
```

### On Merge to Main (`ci.yml` — index job)

```
Index Job
├── Rebuild symbols.json + file_map.json
└── Auto-commit updated index [skip ci]
```

### Daily at 6am UTC (`entropy_gc.yml`)

```
Entropy GC Job
├── Build repo index
├── Run entropy scan (all linters)
├── Analyze violations (CleanerAgent)
├── Open cleanup PRs (one per principle cluster)
├── Update QUALITY_SCORE.md
└── Upload results as artifact
```

---

<p align="center">
  <strong>Ouroboros</strong> — the serpent that eats its own tail.<br/>
  A system that builds, reviews, and improves itself.
</p>
