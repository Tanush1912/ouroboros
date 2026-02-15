# Plan: Project Ouroboros — Agent-First Engineering Infrastructure

## Context

Inspired by the OpenAI "Harness Engineering" blog post. Goal: build a repository-native software factory using
Gemini 3 Flash on Vertex AI, PydanticAI for structured agent outputs, LangGraph for workflow orchestration, and
Logfire for observability of the agent system itself.

The name "Ouroboros" is intentional — the system manages and improves itself.

---

## Monitoring Decision: Logfire over LangSmith

**Logfire** is the correct choice here because:
- Built by the Pydantic team — first-class PydanticAI instrumentation (zero-config)
- OpenTelemetry native — traces integrate with the app's own OTel pipeline
- Structured data model — Pydantic models surface directly in trace spans
- Single dashboard for both agent traces AND app observability

LangSmith is better when you're deeply in the LangChain ecosystem and need prompt dataset management. Since we're
using PydanticAI as the core agent layer, Logfire is the natural fit.

---

## Repo Bootstrap (first execution steps)

```bash
cd /Volumes/tanush-ssd/repos/project-ouroboros
git init
git branch -M main
gh repo create project-ouroboros --private --source=. --remote=origin
```

---

## Target Repository Structure

```
project-ouroboros/
├── AGENTS.md                    # ~100-line agent entry point (table of contents)
├── ARCHITECTURE.md              # Domain/layer map with dependency rules
│
├── docs/
│   ├── design-docs/
│   │   ├── index.md             # Catalogued with verification status
│   │   └── core-beliefs.md      # Agent-first operating principles
│   ├── exec-plans/
│   │   ├── active/              # In-progress execution plans (versioned)
│   │   └── completed/           # Completed plans (archived, never deleted)
│   ├── references/              # llms.txt-style compressed external docs
│   │   ├── pydantic-ai-llms.txt
│   │   ├── langgraph-llms.txt
│   │   └── vertexai-llms.txt
│   ├── DESIGN.md
│   ├── PLANS.md                 # How to read/write execution plans
│   ├── QUALITY_SCORE.md         # Per-domain quality grades (auto-updated)
│   └── GOLDEN_PRINCIPLES.md     # Machine-checkable enforcement rules
│
├── agents/
│   ├── core/
│   │   ├── agent.py             # LangGraph StateGraph definition
│   │   ├── state.py             # Typed state schema (Pydantic)
│   │   ├── config.py            # Vertex AI + model config
│   │   ├── context_builder.py   # build_context(task) → scoped token budget
│   │   └── guards.py            # Rate-limit + iteration + tool-call guards
│   ├── models/                  # PydanticAI output models (one per agent role)
│   │   ├── planner.py           # PlanOutput, ExecutionStep
│   │   ├── implementer.py       # ImplementOutput, FileChange
│   │   ├── reviewer.py          # ReviewOutput, ReviewComment
│   │   ├── validator.py         # ValidationOutput, TestResult
│   │   ├── cleaner.py           # CleanupOutput, EntropyViolation
│   │   └── cost.py              # CostSummary (tokens_in, tokens_out, cost_usd)
│   ├── workers/                 # PydanticAI agents (one per role)
│   │   ├── planner.py           # Decomposes task into typed steps
│   │   ├── implementer.py       # Writes code, returns FileChange[]
│   │   ├── reviewer.py          # Reviews diff, returns ReviewOutput
│   │   ├── validator.py         # Runs tests/lint, returns ValidationOutput
│   │   └── cleaner.py           # Detects entropy, returns CleanupOutput
│   ├── tools/                   # Clearly defined @tool functions
│   │   ├── registry.py          # ToolRegistry — capability catalog for planner
│   │   ├── fs.py                # read_file, write_file, list_dir, search_repo
│   │   ├── shell.py             # run_tests, run_lint, run_build, run_command
│   │   ├── git.py               # git_status, commit, push, open_pr,
│   │   │                        #   get_pr_diff, get_pr_comments, merge_pr
│   │   ├── browser.py           # take_screenshot, snapshot_dom, drive_ui_flow
│   │   └── observability.py     # query_logs (LogQL), query_metrics (PromQL)
│   └── workflows/
│       ├── ralph_loop.py        # Main PR lifecycle LangGraph workflow
│       ├── reviewer_loop.py     # Agent-to-agent review workflow
│       └── entropy_gc.py        # Entropy scanning + cleanup PR workflow
│
├── repo_index/
│   ├── build_index.py           # Generates symbols.json + file_map.json
│   ├── symbols.json             # Symbol → file + line (via tree-sitter/ctags)
│   └── file_map.json            # file → domain, layer, imports, exports
│
├── tests/
│   ├── lint/                    # Unit tests for arch_lint, golden_lint
│   └── agent_eval/              # Deterministic agent behavior tests
│       ├── test_bug_fix.py      # Agent receives buggy code → asserts fix
│       ├── test_feature_gen.py  # Agent receives feature prompt → asserts output
│       └── test_entropy_gc.py   # Introduce violation → assert cleanup PR opens
│
├── harness/
│   ├── sandbox/
│   │   └── docker-compose.yml   # Per-worktree ephemeral app isolation
│   └── observability/
│       ├── docker-compose.yml   # VictoriaLogs + VictoriaMetrics + Vector + Grafana
│       └── vector.toml          # Log/metric routing from app to storage
│
├── lint/
│   ├── arch_lint.py             # AST-based layer dependency checker
│   ├── golden_lint.py           # Checks golden principles (dedup, size, naming)
│   ├── doc_lint.py              # Checks docs are cross-linked and not stale
│   ├── rules.py                 # Named rules with AGENT_REMEDIATION fields
│   └── run_lint.py              # CLI runner (used by CI and agents)
│
├── scripts/
│   ├── worktree_up.sh           # Spin up isolated per-worktree env
│   └── worktree_down.sh         # Tear down and remove volumes
│
├── .github/
│   └── workflows/
│       ├── ci.yml               # lint + tests + arch enforcement on every PR
│       └── entropy_gc.yml       # Scheduled entropy scan (cron: daily)
│
├── pyproject.toml               # uv + ruff + pytest config
└── requirements.txt             # pydantic-ai, langgraph, logfire, vertexai, etc.
```

---

## Component Design

### 1. Model Layer: Vertex AI + Gemini 3 Flash

All agents use `gemini-3.0-flash` via Vertex AI (not the direct API):

```python
# agents/core/config.py
import vertexai
from pydantic_ai.models.vertexai import VertexAIModel

vertexai.init(project=GCP_PROJECT, location="us-central1")
model = VertexAIModel("gemini-3.0-flash")
```

Vertex AI provides:
- Production-grade rate limits (holds up under high-throughput agent runs)
- IAM-based auth (no API key to rotate)
- Regional isolation
- Usage quotas per project

---

### 2. PydanticAI Structured Outputs

Every agent role returns a typed Pydantic model — no text parsing anywhere:

```python
# agents/models/planner.py
class ExecutionStep(BaseModel):
    description: str
    files_affected: list[str]
    tool: Literal["fs", "shell", "git", "browser"]
    expected_output: str

class PlanOutput(BaseModel):
    task_summary: str
    steps: list[ExecutionStep]
    test_strategy: str
    risk_level: Literal["low", "medium", "high"]
    requires_human_review: bool

# agents/models/reviewer.py
class ReviewComment(BaseModel):
    file: str
    line: int | None
    severity: Literal["nit", "minor", "major", "blocking"]
    comment: str
    suggested_fix: str | None

class ReviewOutput(BaseModel):
    approved: bool
    comments: list[ReviewComment]
    blocking_issues: list[str]
    summary: str

# agents/models/validator.py
class TestResult(BaseModel):
    passed: bool
    failures: list[str]
    coverage: float | None

class LintResult(BaseModel):
    passed: bool
    violations: list[str]  # Includes AGENT_REMEDIATION instructions

class ValidationOutput(BaseModel):
    tests: TestResult
    lint: LintResult
    arch_lint: LintResult
    overall_pass: bool
    next_action: Literal["proceed", "retry", "escalate"]
```

The `next_action` field in `ValidationOutput` drives LangGraph's conditional edges — no string parsing, pure type
routing.

---

### 3. LangGraph Workflow (Ralph Loop)

**File:** `agents/workflows/ralph_loop.py`

```
[start]
   ↓
plan_node           (PlannerAgent → PlanOutput)
   ↓
implement_node      (ImplementerAgent → ImplementOutput)
   ↓
validate_node       (ValidatorAgent → ValidationOutput)
   ↓
[conditional]
  → "retry" → implement_node       (max 5 iterations)
  → "escalate" → human_checkpoint
  → "proceed" → open_pr_node
   ↓
open_pr_node        (git tool: gh pr create)
   ↓
review_loop_node    (ReviewerAgent → ReviewOutput)
   ↓
[conditional]
  → approved=False → implement_node (address feedback)
  → approved=True → merge_node
   ↓
merge_node          (git tool: gh pr merge --squash)
   ↓
[done]
```

LangGraph state:

```python
class RalphState(TypedDict):
    task: str
    plan: PlanOutput | None
    files_changed: list[FileChange]
    validation: ValidationOutput | None
    review: ReviewOutput | None
    pr_url: str | None
    iteration_count: int
    review_iteration_count: int
    status: Literal["planning", "implementing", "validating",
                    "reviewing", "merging", "done", "escalated"]
```

---

### 4. Repository Index

**Files:** `repo_index/build_index.py`, `repo_index/symbols.json`, `repo_index/file_map.json`

Generated on every commit via CI (or on-demand by the agent):

```bash
# build_index.py uses:
# - tree-sitter: parse AST for classes, functions, types
# - ctags: fallback symbol extraction
# - ripgrep: fast file discovery and cross-reference scanning
```

Output:

```json
// symbols.json
{
  "ValidationOutput": {"file": "agents/models/validator.py", "line": 42, "kind": "class"},
  "run_lint":         {"file": "agents/tools/shell.py",      "line": 18, "kind": "function"}
}

// file_map.json
{
  "agents/workers/planner.py": {
    "domain": "agents",
    "layer": "workers",
    "imports": ["agents.models.planner", "agents.tools.registry"],
    "exports": ["PlannerWorker", "run_planner"]
  }
}
```

Tool exposed to agents:

```python
@tool
def search_symbol(name: str) -> SymbolLocation | None:
    """Look up a symbol by name. Returns file + line. Never reads the whole repo."""
```

This replaces the agent's instinct to `read_file` every file it can find. Dramatically reduces token usage and
navigation time.

---

### 5. Context Builder

**File:** `agents/core/context_builder.py`

Agents never receive raw file dumps. They receive a **budget-aware context package**:

```python
class TaskContext(BaseModel):
    task: str
    relevant_files: list[FileSnippet]    # Trimmed to relevant sections
    relevant_docs: list[DocReference]    # ARCHITECTURE.md sections, design docs
    arch_rules: list[str]                # Active lint rules for touched layers
    active_plans: list[str]              # Exec plans referencing this domain
    available_tools: list[ToolSummary]   # From registry (not all tools, just applicable)
    token_budget_remaining: int

def build_context(task: str, max_tokens: int = 8000) -> TaskContext:
    """
    1. Parse task to extract intent + domain hints
    2. Query repo_index for relevant symbols/files
    3. Pull architecture rules for touched layers
    4. Attach active exec-plans for the domain
    5. Trim everything to fit within max_tokens budget
    """
```

The context builder is the **gatekeeper for token spend**. Without it, agents read 50 files and burn context on
noise. With it, they receive exactly what they need.

---

### 6. Clearly Defined Tool Signatures + Capability Registry

**File:** `agents/tools/registry.py`

The planner queries the registry to understand what tools exist before making a plan — prevents hallucinating tool
names:

```python
class ToolCapability(BaseModel):
    name: str
    description: str
    input_schema: dict
    output_type: str
    category: Literal["fs", "shell", "git", "browser", "observability", "index"]
    requires_sandbox: bool          # Does this tool need the Docker stack running?

class ToolRegistry:
    def all_tools(self) -> list[ToolCapability]: ...
    def tools_for_category(self, category: str) -> list[ToolCapability]: ...
    def get_tool(self, name: str) -> ToolCapability | None: ...

REGISTRY = ToolRegistry()  # Singleton, imported by planner and context_builder
```

Planner receives `available_tools` from `build_context()`, sourced from the registry. It can only reference tools
that exist. If a tool is added later, the registry updates automatically — no prompt editing required.

---

### 7. Tool Signatures (Full Catalog)

All tools are `@tool`-decorated functions with full type annotations and registered in `ToolRegistry`:

```python
# agents/tools/fs.py
@tool
def read_file(path: str) -> str:
    """Read a file from the repository. Returns file contents."""

@tool
def write_file(path: str, content: str) -> WriteResult:
    """Write content to a file. Creates parent dirs if needed."""

@tool
def search_repo(query: str, file_pattern: str = "**/*") -> list[SearchMatch]:
    """Search repo contents using ripgrep. Returns file + line matches."""

# agents/tools/shell.py
@tool
def run_tests(path: str = ".") -> TestResult:
    """Run pytest. Returns structured pass/fail with failure details."""

@tool
def run_lint(path: str = ".") -> LintResult:
    """Run ruff + arch_lint + golden_lint. Returns violations with remediations."""

@tool
def run_build() -> BuildResult:
    """Build the application. Returns success/failure + build log."""

# agents/tools/git.py
@tool
def git_status() -> GitStatus:
    """Returns changed files, staged files, current branch."""

@tool
def commit(message: str, files: list[str]) -> CommitResult:
    """Stage specific files and create a commit."""

@tool
def open_pr(title: str, body: str, base: str = "main") -> PRResult:
    """Open a pull request via gh CLI. Returns PR URL and number."""

@tool
def get_pr_comments(pr_number: int) -> list[PRComment]:
    """Fetch review comments on a PR. Returns structured comment list."""

@tool
def merge_pr(pr_number: int, strategy: Literal["squash", "merge"] = "squash") -> MergeResult:
    """Merge a pull request."""

# agents/tools/browser.py
@tool
def take_screenshot(url: str) -> ScreenshotResult:
    """Navigate to URL and capture screenshot. Returns base64 image."""

@tool
def snapshot_dom(url: str) -> DOMSnapshot:
    """Capture DOM accessibility tree. Returns structured DOM."""

@tool
def drive_ui_flow(url: str, steps: list[UIAction]) -> UIFlowResult:
    """Execute a sequence of UI actions. Returns pass/fail + screenshots."""

# agents/tools/observability.py
@tool
def query_logs(logql: str, duration: str = "1h") -> list[LogLine]:
    """Query VictoriaLogs with LogQL. E.g. '{service="api"} |= "error"'"""

@tool
def query_metrics(promql: str, duration: str = "1h") -> MetricResult:
    """Query VictoriaMetrics with PromQL. E.g. 'rate(http_requests_total[5m])'"""
```

---

### 8. Rate-Limit & Failure Guards

**File:** `agents/core/guards.py`

Agents can loop forever without hard limits. These are enforced at the LangGraph state level — not optional:

```python
# Hard limits (constants, not config — intentionally not tunable at runtime)
MAX_IMPLEMENT_ITERATIONS = 5    # implement → validate → retry cycles
MAX_REVIEW_ITERATIONS = 3       # review → fix → re-review cycles
MAX_TOOL_CALLS_PER_NODE = 50    # Tools called in a single LangGraph node
MAX_TOTAL_TOOL_CALLS = 200      # Across entire workflow run

class GuardResult(BaseModel):
    allowed: bool
    reason: str | None           # Populated when allowed=False
    action: Literal["continue", "escalate", "abort"]

def check_guards(state: RalphState) -> GuardResult:
    if state.iteration_count >= MAX_IMPLEMENT_ITERATIONS:
        return GuardResult(allowed=False, reason="Max implement iterations reached", action="escalate")
    if state.total_tool_calls >= MAX_TOTAL_TOOL_CALLS:
        return GuardResult(allowed=False, reason="Tool call budget exhausted", action="abort")
    return GuardResult(allowed=True, reason=None, action="continue")
```

Guards run at the start of every LangGraph node via a `pre_node_guard` wrapper. When `action="escalate"`, the
workflow transitions to `human_checkpoint`. When `action="abort"`, it writes a failure report and exits cleanly.

---

### 9. Cost Awareness

**File:** `agents/models/cost.py`

Every workflow run produces a `CostSummary`. Agents can query their own cost and factor it into decisions:

```python
class CostSummary(BaseModel):
    tokens_in: int
    tokens_out: int
    cost_usd: float              # Calculated from Vertex AI pricing
    model: str
    task: str
    workflow: str
    duration_seconds: float
    iterations: int
    tool_calls: int

class RunMetrics(BaseModel):
    cost: CostSummary
    per_node_costs: dict[str, CostSummary]   # Cost breakdown by LangGraph node
    highest_cost_node: str
```

Logfire receives `RunMetrics` after every completed workflow. Over time this builds a dataset of:
- Cost per PR by task type
- Which nodes burn the most tokens
- Cost regression when model or prompts change

The cleaner agent can also detect when a domain is consistently expensive and flag it in `QUALITY_SCORE.md`.

---

### 10. Agent Eval Tests

**Directory:** `tests/agent_eval/`

Deterministic behavioral tests that run in CI. Each test:
1. Sets up a controlled repo state (fixture)
2. Runs a specific agent/workflow with a fixed prompt
3. Asserts on structured outputs — not text matching

```python
# tests/agent_eval/test_bug_fix.py
def test_agent_fixes_off_by_one(tmp_repo):
    """Agent receives a function with an off-by-one error. Must fix it."""
    write_fixture(tmp_repo, "utils/counter.py", BUGGY_COUNTER_CODE)
    result = run_ralph_loop(task="Fix the off-by-one error in utils/counter.py", repo=tmp_repo)

    assert result.status == "done"
    assert result.iteration_count <= 3
    assert result.pr_url is not None
    # Verify the fix is structurally correct
    fixed = read_file(tmp_repo, "utils/counter.py")
    assert "range(n)" in fixed  # Not asserting exact code, asserting intent

# tests/agent_eval/test_entropy_gc.py
def test_gc_detects_duplicate_utility(tmp_repo):
    """Introduce GP-001 violation, run GC, assert cleanup PR is opened."""
    write_fixture(tmp_repo, "billing/utils.py", DUPLICATE_LOGGER)
    write_fixture(tmp_repo, "auth/utils.py", DUPLICATE_LOGGER)

    result = run_entropy_gc(repo=tmp_repo)

    gp001_violations = [v for v in result.violations if v.principle == "GP-001"]
    assert len(gp001_violations) >= 1
    assert gp001_violations[0].auto_fixable is True
    assert len(result.recommended_prs) >= 1
```

These tests track:
- **Task success rate** (did the agent complete the task?)
- **Iterations required** (is the agent getting more efficient over time?)
- **Regressions** (did a model/prompt change break behavior?)

Run in CI on every PR. Results are surfaced in `docs/QUALITY_SCORE.md` under "Agent Eval".

---

### 11. Entropy & Garbage Collection

This is a first-class subsystem, not an afterthought.

**Golden Principles** (`docs/GOLDEN_PRINCIPLES.md`) define machine-checkable rules:

```
GP-001: No duplicate utility functions across packages
GP-002: No file exceeds 500 lines
GP-003: No hand-rolled helpers that duplicate shared packages
GP-004: No YOLO data access (all external data validated at boundary)
GP-005: Structured logging only (no print() outside scripts/)
GP-006: Schema types follow *Schema/*Type naming convention
GP-007: No dead imports
GP-008: All docs reference real code that still exists
GP-009: All exec-plans in active/ have been updated in last 7 days
GP-010: QUALITY_SCORE.md reflects actual current state
```

**Entropy Scanner** (`agents/workers/cleaner.py`):

```python
class EntropyViolation(BaseModel):
    principle: str           # e.g., "GP-001"
    file: str
    description: str
    suggested_fix: str
    auto_fixable: bool       # Can the agent fix this without human input?
    severity: Literal["low", "medium", "high"]

class CleanupOutput(BaseModel):
    violations: list[EntropyViolation]
    quality_scores: dict[str, float]  # domain → score 0-10
    recommended_prs: list[str]        # One PR description per auto-fixable cluster
    human_review_needed: list[str]    # Non-auto-fixable issues
```

**Entropy GC Workflow** (`agents/workflows/entropy_gc.py`):

```
[scan]
   ↓
entropy_scan_node      (CleanerAgent → CleanupOutput)
   ↓
cluster_violations     (group by principle + domain)
   ↓
for each auto-fixable cluster:
   → implement_fix_node
   → validate_node
   → open_pr_node (tiny, targeted, < 1 min review)
   ↓
update_quality_score_node  (writes docs/QUALITY_SCORE.md)
   ↓
notify_human_if_needed
```

Runs daily via `.github/workflows/entropy_gc.yml`. Each cleanup PR is:
- Atomic (one principle violation cluster)
- Titled: `[gc] GP-001: remove duplicate logging utilities in billing/`
- Auto-mergeable if tests pass (no human required)

---

### 12. Logfire Integration

```python
import logfire

logfire.configure()
logfire.instrument_pydantic_ai()   # Auto-traces all PydanticAI agent calls
logfire.instrument_httpx()         # Traces Vertex AI API calls
```

Every agent run creates a trace with:
- Model used, tokens in/out
- Tool calls with inputs/outputs (as Pydantic models, not strings)
- LangGraph node transitions
- Validation outcomes

This gives full visibility into: why an agent failed, which tools it called, how many iterations a task took, token
cost per PR.

---

### 13. Observability Stack (Harness)

**File:** `harness/observability/docker-compose.yml`

```yaml
services:
  vector:
    image: timberio/vector:latest
    # Routes app logs to VictoriaLogs, metrics to VictoriaMetrics
  victoria-logs:
    image: victoriametrics/victoria-logs:latest
    # LogQL HTTP API at :9428
  victoria-metrics:
    image: victoriametrics/victoria-metrics:latest
    # PromQL HTTP API at :8428
  grafana:
    image: grafana/grafana:latest
    # Human dashboard at :3000
```

Per-worktree isolation: `scripts/worktree_up.sh` allocates unique port ranges. `scripts/worktree_down.sh` removes
volumes. Agent never shares log context with parallel runs.

---

### 14. Architecture Enforcement Linter

**File:** `lint/arch_lint.py`

Enforces the layered dependency model:
```
types → config → repo → service → runtime → ui
```

Cross-cutting concerns enter only via `providers/`.

Error message format (agent-readable):

```
ARCH-VIOLATION: agents/workers/planner.py imports from agents/workers/reviewer.py
RULE: Workers cannot cross-import. Extract shared logic to agents/core/.
REMEDIATION: Move shared type X to agents/models/shared.py and import from there.
DOCS: See ARCHITECTURE.md#worker-isolation
```

The `REMEDIATION` field is the critical piece — the agent reads this and knows exactly how to fix the violation
without human guidance.

---

## Tech Stack

| Layer | Tool | Rationale |
|---|---|---|
| Language Model | Gemini 3 Flash via Vertex AI | Production-grade quotas, IAM auth |
| Agent Output | PydanticAI | Typed structured outputs, Logfire integration |
| Agent Orchestration | LangGraph | Explicit state machine, conditional routing |
| Agent Monitoring | Logfire | Native PydanticAI tracing, OTel native |
| Repo Index | tree-sitter + ctags + ripgrep | Fast symbol lookup without full file reads |
| Language | Python 3.12 | |
| Package Manager | uv | Fast, lockfile-based |
| Linter/Formatter | ruff | Fast, covers isort + flake8 + more |
| Git Automation | gh CLI | Programmatic PR management |
| Browser Automation | Playwright | DOM snapshots + screenshots |
| App Observability | VictoriaLogs + VictoriaMetrics + Vector | LogQL/PromQL queryable by agent |
| CI | GitHub Actions | Lint + tests on every PR, entropy GC on schedule |
| Containerization | Docker + Compose | Per-worktree isolation |

---

## Build Phases

### Phase 1: Foundation (Days 1-3)
- [ ] `git init` + `gh repo create project-ouroboros --private`
- [ ] Repo structure + AGENTS.md + ARCHITECTURE.md + core-beliefs.md
- [ ] `pyproject.toml` with uv, ruff, pytest
- [ ] Vertex AI config + Gemini 3 Flash connection
- [ ] PydanticAI model definitions (all 5 agent roles + CostSummary)
- [ ] `agents/tools/registry.py` — ToolRegistry + all tool stubs registered
- [ ] Core tool definitions with Pydantic return types (fs, shell, git)
- [ ] `agents/core/guards.py` — iteration + tool-call hard limits
- [ ] Basic LangGraph agent loop (plan → implement → validate) with guards
- [ ] Logfire integration + PydanticAI instrumentation

### Phase 2: Repo Index + Context Builder (Days 2-4)
- [ ] `repo_index/build_index.py` — tree-sitter + ctags + ripgrep
- [ ] `repo_index/symbols.json` + `repo_index/file_map.json` generated
- [ ] `agents/tools/fs.py` — `search_symbol` tool using index
- [ ] `agents/core/context_builder.py` — `build_context(task)` with token budget
- [ ] Context builder wired into planner worker

### Phase 3: Architecture Enforcement (Days 4-6)
- [ ] `lint/arch_lint.py` — layer checker with REMEDIATION messages
- [ ] `lint/golden_lint.py` — GP-001 through GP-010
- [ ] `lint/doc_lint.py` — stale doc detection
- [ ] `lint/rules.py` — centralized rule registry
- [ ] CI workflow: lint + tests on every PR

### Phase 4: Full Ralph Loop (Days 6-9)
- [ ] `agents/workflows/ralph_loop.py` — complete PR lifecycle
- [ ] `agents/workflows/reviewer_loop.py` — agent-to-agent review
- [ ] PR open/comment/merge via gh tools
- [ ] Human escalation checkpoint in LangGraph
- [ ] Cost tracking: `RunMetrics` emitted at workflow end → Logfire

### Phase 5: Observability Harness (Days 8-11)
- [ ] `harness/observability/docker-compose.yml`
- [ ] `agents/tools/observability.py` — LogQL + PromQL tools
- [ ] `scripts/worktree_up.sh` / `worktree_down.sh`
- [ ] Vector log routing config

### Phase 6: Browser Validation (Days 10-12)
- [ ] `agents/tools/browser.py` — Playwright tools
- [ ] UI validation node in Ralph Loop
- [ ] Before/after screenshot comparison

### Phase 7: Entropy GC + Agent Eval (Days 11-15)
- [ ] `agents/workflows/entropy_gc.py`
- [ ] `docs/GOLDEN_PRINCIPLES.md` — all 10 principles
- [ ] `docs/QUALITY_SCORE.md` — initial baseline scores
- [ ] `.github/workflows/entropy_gc.yml` — scheduled daily
- [ ] Auto-merge for GP-tagged cleanup PRs
- [ ] `tests/agent_eval/test_bug_fix.py`
- [ ] `tests/agent_eval/test_feature_gen.py`
- [ ] `tests/agent_eval/test_entropy_gc.py`

---

## Verification Plan

1. **Vertex AI connection:** `python -c "from agents.core.config import model; print(model)"` → no error

2. **Structured output:** Run planner worker on "add a logging utility" → returns `PlanOutput` with typed fields, not
   raw text

3. **Repo index:** `python repo_index/build_index.py` → `symbols.json` populated; `search_symbol("ValidationOutput")`
   returns correct file + line

4. **Context builder:** `build_context("fix the login endpoint")` → returns `TaskContext` with relevant files only,
   under token budget

5. **Guards:** Set `MAX_IMPLEMENT_ITERATIONS=1`, run a failing task → workflow transitions to `escalated` after 1
   retry, not infinite loop

6. **Cost tracking:** Run one full workflow → Logfire shows `RunMetrics` span with `cost_usd` populated

7. **Tool registry:** `REGISTRY.all_tools()` → returns all registered tools; planner only references names from this
   list

8. **Logfire traces:** Run one agent loop → Logfire dashboard shows full trace with tool calls and model spans

9. **Arch lint:** Create a file that imports across layers → `python lint/run_lint.py` → fails with REMEDIATION
   message

10. **Ralph Loop e2e:** Prompt: "add a /health endpoint that returns 200" → agent creates file, runs tests, opens PR,
    reviewer approves, PR merges

11. **Agent eval tests:** `pytest tests/agent_eval/` → all 3 eval tests pass, metrics logged

12. **Entropy GC:** Manually add a duplicate utility function → run entropy_gc workflow → cleanup PR opens
    automatically

13. **Observability:** Spin up `docker compose` stack, generate logs → agent queries `{service="api"} |= "error"` →
    returns structured results
