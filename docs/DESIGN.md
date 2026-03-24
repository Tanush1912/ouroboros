# System Design Overview

Ouroboros is an agent-first software factory. Autonomous LLM-powered agents plan, implement, review, validate, and merge code changes through a structured adaptive pipeline. The system is self-referential — agents can improve the agent infrastructure itself.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language Model | Gemini 2.5 Flash via Vertex AI |
| Agent Framework | PydanticAI 1.44 (GoogleModel, provider=`google-vertex`) |
| Orchestration | LangGraph StateGraph |
| Monitoring | Logfire (OTel-native PydanticAI tracing) |
| Observability | VictoriaLogs + VictoriaMetrics + Vector + Grafana (Docker) |
| Package Manager | uv |
| Linter | ruff + custom arch/golden/doc/workflow linters |
| Type Checker | pyright (basic) |
| Tests | pytest |
| Browser | Playwright |

---

## Adaptive Pipeline

The main workflow (`agents/workflows/ralph_loop.py`) orchestrates the full PR lifecycle via a LangGraph StateGraph. The planner dynamically controls which stages run by setting `skip_stages`.

```
plan → [reproduce] → implement → [test_writer] → validate
  → [mutation] → [perf] → [ui] → open_pr → [review] → merge
```

Stages in brackets are skippable via `PlanOutput.skip_stages`. Routing logic lives in `agents/workflows/ralph_routing.py`.

### Pipeline Nodes

| Node | Purpose | Max Iterations |
|------|---------|---------------|
| `plan_node` | Decompose task into executable steps via planner agent | 1 |
| `reproduce_node` | Run pytest to reproduce bugs, capture traceback/evidence | 1 |
| `implement_node` | Generate/modify code via implementer agent, apply to disk | 5 |
| `test_writer_node` | Write adversarial tests via test writer agent | 3 |
| `validate_node` | Run tests + lint + quality gate + contracts (deterministic, no LLM) | — |
| `mutation_validate_node` | Apply random AST mutations, verify tests catch them | 1 |
| `perf_validate_node` | Run pytest-benchmark, compare against baseline | 1 |
| `ui_validate_node` | Take Playwright screenshots for visual verification | 1 |
| `open_pr_node` | Commit changes, open PR via `gh` CLI | 1 |
| `review_loop_node` | Review PR diff via reviewer agent | 3 |
| `merge_node` | Merge PR via `gh pr merge --squash` | 1 |
| `human_checkpoint` | Halt for human intervention (guard violations, escalations) | — |

### Routing Logic

Routing is deterministic and driven by typed outputs, not LLM decisions:

- **After plan**: bug-fix keywords → `reproduce_node`, otherwise → `implement_node`
- **After validate**: `ValidationOutput.next_action` determines proceed/retry/escalate
  - Retry targets are determined by failure location (test files → `test_writer_node`, code → `implement_node`)
- **After mutation**: kill_rate < 0.6 → `test_writer_node` for stronger tests
- **After review**: not approved + iterations remaining → `implement_node` to address feedback
- **Skip resolution**: `_resolve_next_stage()` walks post-validation stages, skipping any in `skip_stages`

---

## Architectural Layers

Strict dependency ordering enforced at CI time by `lint/arch_lint.py`:

```
models → config → core → tools → workers → workflows → cli/scripts
```

| Layer | Location | May Import From | Key Rule |
|-------|----------|----------------|----------|
| models | `agents/models/*` | stdlib, pydantic | Pure data schemas only |
| config | `agents/core/config.py` | models, stdlib | Single source of truth for LLM |
| core | `agents/core/*` | models, config | Shared infrastructure |
| tools | `agents/tools/*` | models, core | Stateless utilities; **cannot import workers** |
| workers | `agents/workers/*` | models, core, tools | PydanticAI agents; **cannot cross-import** |
| workflows | `agents/workflows/*` | everything above | LangGraph state machines |

Workers that share logic must extract it to `agents/core/`. Workflows may import tools directly for mechanical side-effects (git, lint) that don't involve LLM reasoning.

---

## Core Infrastructure

### Model Configuration (`agents/core/config.py`)

Single point of truth for Vertex AI access:

```python
get_model() → GoogleModel  # Reads GCP_PROJECT, GCP_LOCATION, OUROBOROS_MODEL
```

### Workflow State (`agents/core/state.py`)

`RalphState` is a TypedDict carrying all pipeline state:

- `task`, `plan`, `files_changed`, `validation`, `review` — pipeline data
- `iteration_count`, `review_iteration_count` — loop counters
- `total_tool_calls`, `total_tokens_in/out`, `estimated_cost_usd` — metrics
- `cost_budget_usd` — hard spend limit (default: $2.00/run)
- `status` — current pipeline state
- `error_log` — accumulated errors
- `node_token_usage`, `node_tool_calls` — per-node accounting
- `skip_stages` — planner-controlled stage skipping

### Guard Rails (`agents/core/guards.py`)

Hard limits enforced at every node entry via `pre_node_guard()`:

| Guard | Default | On Violation |
|-------|---------|-------------|
| Max implement iterations | 5 | escalate |
| Max review iterations | 3 | escalate |
| Max test writer iterations | 3 | escalate |
| Max tool calls per node | 50 | abort |
| Max total tool calls | 200 | abort |
| Max cost per run | $2.00 | abort |

All limits are configurable via `OUROBOROS_*` environment variables. Exempt nodes: `post_mortem_node`, `human_checkpoint`.

### Context Builder (`agents/core/context_builder.py`)

Produces scoped, token-budgeted context for each agent:

```python
build_context(task, worker_name) → TaskContext
```

`TaskContext` includes relevant file snippets, design docs, architecture rules, active plans, and a filtered tool catalog. Tool visibility is controlled per-worker — the planner sees all tools but workers only see agent-callable ones.

### Workflow Helpers (`agents/core/workflow_helpers.py`)

- `retry_on_transient(fn)` — retries on transient HTTP/model errors (3 attempts, backoff: 2s/5s/10s)
- `apply_file_changes(changes, root)` — applies create/modify/delete to disk with path validation
- `accumulate_usage(state, usage, node_name, tool_calls)` — tracks tokens and cost per node

---

## Agent Workers

Workers are pure reasoning functions: they take context, call the LLM, and return typed Pydantic outputs. They are stateless and session-agnostic.

### Planner (`agents/workers/planner.py`)

Decomposes a task into an executable plan. Queries the repo index to ground its plan in real files and symbols.

**Output**: `PlanOutput` — steps, skip_stages, behavioral_specs, risk_level, commit_type, requires_browser_validation

Each `ExecutionStep` specifies files affected, tool category, and expected output. `BehavioralSpec` entries become machine-verifiable contracts checked during validation.

### Implementer (`agents/workers/implementer.py`)

Generates code changes following the plan. Receives previous validation failures on retry iterations to address specific issues.

**Output**: `ImplementOutput` — `list[FileChange]` (create/modify/delete), commit_message, implementation_notes

### Test Writer (`agents/workers/test_writer.py`)

Writes adversarial tests designed to break the implementation. Focuses on edge cases, error conditions, and boundary values. Iterates if test quality score falls below 60.

**Output**: `TestWriterOutput` — test files, test strategy, confidence score

### Validator (`agents/workers/validator.py`)

Deterministic verification — no LLM calls. Runs tests, lint, test quality gate, and behavioral contracts in parallel. Produces a `next_action` (proceed/retry/escalate) based on results.

### Reviewer (`agents/workers/reviewer.py`)

Reviews PR diffs against the original task and plan. Returns structured feedback with per-file, per-line comments and severity levels (nit/minor/major/blocking).

**Output**: `ReviewOutput` — approved, comments, blocking_issues, has_meaningful_tests

---

## Agent-Callable Tools

Tools that agents can invoke during execution (registered in `agents/tools/`):

| Tool | Function | Purpose |
|------|----------|---------|
| `read_file` | `fs.read_file(path)` | Read file content (path-validated within repo) |
| `list_dir` | `fs.list_dir(path)` | List directory contents |
| `search_repo` | `fs.search_repo(query, file_pattern)` | ripgrep-backed regex search |
| `search_symbol` | `fs.search_symbol(name)` | Symbol lookup via repo index |

### System Tools (used by workflow nodes, not agents)

| Tool | Module | Purpose |
|------|--------|---------|
| `run_tests` | `shell.py` | pytest runner with structured output |
| `run_lint` | `shell.py` | ruff + arch_lint + golden_lint |
| `commit` | `git.py` | Stage and commit changes |
| `open_pr` | `git.py` | Create PR via `gh` CLI |
| `merge_pr` | `git.py` | Merge PR via `gh pr merge` |
| `analyze_test_quality` | `test_quality.py` | AST-based test quality scoring (zero LLM cost) |
| `verify_contracts` | `contract_verifier.py` | Deterministic behavioral spec checks |
| `run_mutation_sampling` | `mutation_sampler.py` | Random AST mutation testing |
| `run_benchmark` | `benchmark.py` | pytest-benchmark runner |
| `query_logs` | `observability.py` | LogQL queries against VictoriaLogs |
| `query_metrics` | `observability.py` | PromQL queries against VictoriaMetrics |
| `take_screenshot` | `browser.py` | Playwright screenshot capture |

---

## Typed Communication

All inter-agent communication uses Pydantic models (`agents/models/`). No string parsing anywhere.

| Model | Module | Used By |
|-------|--------|---------|
| `PlanOutput`, `ExecutionStep`, `BehavioralSpec` | `planner.py` | Planner → all downstream nodes |
| `ImplementOutput`, `FileChange` | `implementer.py` | Implementer → validator |
| `TestWriterOutput`, `TestStrategy` | `test_writer.py` | Test writer → validator |
| `ValidationOutput`, `TestResult`, `LintResult` | `validator.py` | Validator → routing |
| `ReviewOutput`, `ReviewComment` | `reviewer.py` | Reviewer → routing |
| `MutationSamplingResult`, `MutantResult` | `mutation.py` | Mutation node → routing |
| `BenchmarkResult`, `PerfComparisonResult` | `benchmark.py` | Perf node → routing |
| `TokenUsage`, `CostSummary`, `RunMetrics` | `cost.py` | All nodes → Logfire |
| `ContractVerificationResult` | `contracts.py` | Validator → routing |
| `TestQualityResult` | `test_quality.py` | Validator → routing |

---

## Quality Enforcement

### Lint Rules (`lint/`)

| Linter | File | What It Checks |
|--------|------|---------------|
| Architecture lint | `arch_lint.py` | Layer dependency violations |
| Golden lint | `golden_lint.py` | GP-001 through GP-010 (machine-checkable principles) |
| Doc lint | `doc_lint.py` | Stale file/symbol references in markdown |
| Workflow lint | `workflow_lint.py` | LangGraph node connectivity, routing validity |

Run via `lint/run_lint.py`:
```bash
uv run python lint/run_lint.py .              # All linters
uv run python lint/run_lint.py --arch-only .   # Architecture only
uv run python lint/run_lint.py --golden-only . # GP-001 to GP-010
```

### Test Quality Gate (`agents/tools/test_quality.py`)

AST-based analysis (zero LLM cost) that checks for:
- Trivial assertions (`assert True`, sole `is not None`)
- Empty test bodies
- Assertion density (min 1.5 per test)
- Edge case coverage (pytest.raises, parametrize, boundary values)
- Untested production files
- Anchor file protection (`tests/anchors/*` cannot be modified by agents)

Pass threshold: score >= 60 (100 base, deductions per violation).

### Mutation Testing (`agents/tools/mutation_sampler.py`)

Verifies test effectiveness by applying random AST mutations (comparison flips, boolean flips, return None) and checking if tests catch them. Pass threshold: kill_rate >= 0.6.

### Behavioral Contracts (`agents/tools/contract_verifier.py`)

The planner emits `BehavioralSpec` entries that are verified deterministically:
- `import_check` — module imports successfully
- `function_exists` — attribute exists on module
- `callable_returns` — function returns expected value/type
- `error_raises` — function raises expected exception
- `file_exists` — file path exists
- `endpoint_returns` — HTTP endpoint returns expected status

---

## Repository Index (`repo_index/`)

Fast, zero-latency code navigation for agents.

**`build_index.py`** produces:
- `symbols.json` — `{name: {file, line, kind}}` for all classes, functions, and constants
- `file_map.json` — `{file: {domain, layer, imports, exports}}`

Agents use `search_symbol(name)` to locate code without reading entire files. The index is incrementally updated via `reindex(paths)` after file modifications.

---

## Observability

### Logfire (Primary)

Native PydanticAI tracing — all agent calls automatically instrumented. Every span carries typed context: task, iteration, tokens, cost. Cost tracking serves as a regression signal.

### Docker Stack (`harness/observability/`)

```
Agent code → Logfire (OTel HTTP exporter)
App code   → Vector → VictoriaLogs (LogQL) / VictoriaMetrics (PromQL) → Grafana
```

Agents can query the observability stack via `query_logs()` and `query_metrics()` to diagnose behavior.

---

## Cost Model

| Metric | Value |
|--------|-------|
| Input pricing | $0.25 / 1M tokens |
| Output pricing | $1.50 / 1M tokens |
| Default budget | $2.00 per run |
| Tracking | Per-node in `node_token_usage`, aggregated in `estimated_cost_usd` |
| Guard | Enforced at every node entry; exceeding budget → abort |

---

## Failure Modes & Recovery

| Scenario | Recovery |
|----------|----------|
| Tests fail (code issue) | Retry → `implement_node` (max 5x) |
| Tests fail (test file issue) | Retry → `test_writer_node` (max 3x) |
| Test quality poor (score < 60) | Retry → `test_writer_node` |
| Behavioral contract fails | Retry → `implement_node` |
| Mutation kill_rate < 0.6 | Retry → `test_writer_node` |
| Anchor tests fail | Escalate immediately to `human_checkpoint` |
| Max iterations / cost exceeded | Guard triggers → `human_checkpoint` |
| Reviewer not satisfied | Retry → `implement_node` (max 3x), then escalate |
| Perf regression | Log warning (informational, does not block) |

---

## Environment Variables

**Required:**
```bash
GCP_PROJECT=ouroboros-490519
GCP_LOCATION=us-central1
LOGFIRE_TOKEN=...
```

**Optional overrides:**
```bash
OUROBOROS_MODEL=gemini-2.5-flash
OUROBOROS_MAX_IMPLEMENT_ITER=5
OUROBOROS_MAX_REVIEW_ITER=3
OUROBOROS_MAX_TEST_WRITER_ITER=3
OUROBOROS_MAX_TOOL_CALLS_NODE=50
OUROBOROS_MAX_TOTAL_TOOL_CALLS=200
OUROBOROS_MAX_COST_USD=2.00
VICTORIA_LOGS_URL=http://localhost:9428
VICTORIA_METRICS_URL=http://localhost:8428
```

---

## Execution Flow

```
Task (str)
  → build_context(task)         # Scoped file snippets, docs, tools, token budget
  → PlannerWorker               # → PlanOutput {steps, skip_stages, behavioral_specs}
  → [ReproduceNode]             # → ReproductionResult (bug-fix tasks only)
  → ImplementerWorker           # → ImplementOutput {files_changed}
  → apply_file_changes()        # Write to disk, reindex symbols
  → [TestWriterWorker]          # → TestWriterOutput {test_files}
  → ValidatorWorker             # → ValidationOutput {next_action} (deterministic)
  → [routing: retry/proceed/escalate]
  → [MutationSampler]           # → MutationSamplingResult {kill_rate}
  → [PerfBenchmark]             # → PerfComparisonResult {verdict}
  → [UIValidation]              # → Screenshots (Playwright)
  → git commit + gh pr create   # → pr_url, pr_number
  → ReviewerWorker              # → ReviewOutput {approved, comments}
  → [routing: merge/retry/escalate]
  → gh pr merge --squash
  → RunMetrics → Logfire
```

Every handoff is a typed Pydantic model. No step produces raw text.
