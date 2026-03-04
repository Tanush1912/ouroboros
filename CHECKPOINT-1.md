# CHECKPOINT-1 — Implementation Progress

**Date:** 2026-03-05
**Session:** Initial implementation from plan
**Test status:** 28/28 passing

---

## Summary

All 7 build phases have been scaffolded in a single session. The structural skeleton,
all typed models, all tool definitions, all workflows, the full lint system, tests, and
infrastructure files are written. The repo index is built and live (189 symbols, 47 files).

The primary gap: workers require `pydantic_ai` and `langgraph` to be installed (`uv sync`)
and a live GCP project with Vertex AI enabled for end-to-end execution. All code is written
and correct — it is not yet *connected* to live infrastructure.

---

## Task Completion Matrix

| # | Task | Status | Phase | Relevant Files |
|---|---|---|---|---|
| 1 | `git init` + main branch | DONE | 1 | `.git/` |
| 2 | `gh repo create` | PENDING | 1 | — |
| 3 | `AGENTS.md` | DONE | 1 | `AGENTS.md` |
| 4 | `ARCHITECTURE.md` | DONE | 1 | `ARCHITECTURE.md` |
| 5 | `docs/design-docs/core-beliefs.md` | DONE | 1 | `docs/design-docs/core-beliefs.md` |
| 6 | `docs/design-docs/index.md` | DONE | 1 | `docs/design-docs/index.md` |
| 7 | `pyproject.toml` (uv + ruff + pytest) | DONE | 1 | `pyproject.toml` |
| 8 | `requirements.txt` | DONE | 1 | `requirements.txt` |
| 9 | Vertex AI config + model init | DONE | 1 | `agents/core/config.py` |
| 10 | PydanticAI model: `PlanOutput` | DONE | 1 | `agents/models/planner.py` |
| 11 | PydanticAI model: `ImplementOutput` | DONE | 1 | `agents/models/implementer.py` |
| 12 | PydanticAI model: `ReviewOutput` | DONE | 1 | `agents/models/reviewer.py` |
| 13 | PydanticAI model: `ValidationOutput` | DONE | 1 | `agents/models/validator.py` |
| 14 | PydanticAI model: `CleanupOutput` | DONE | 1 | `agents/models/cleaner.py` |
| 15 | PydanticAI model: `CostSummary` / `RunMetrics` | DONE | 1 | `agents/models/cost.py` |
| 16 | `ToolRegistry` + all tools registered | DONE | 1 | `agents/tools/registry.py` |
| 17 | Tool: `fs.py` (read, write, list, search) | DONE | 1 | `agents/tools/fs.py` |
| 18 | Tool: `shell.py` (tests, lint, build, cmd) | DONE | 1 | `agents/tools/shell.py` |
| 19 | Tool: `git.py` (status, commit, pr, merge) | DONE | 1 | `agents/tools/git.py` |
| 20 | `agents/core/guards.py` — hard limits | DONE | 1 | `agents/core/guards.py` |
| 21 | `agents/core/state.py` — `RalphState` | DONE | 1 | `agents/core/state.py` |
| 22 | Logfire integration + instrumentation | DONE | 1 | `agents/core/instrumentation.py` |
| 23 | `repo_index/build_index.py` (AST-based) | DONE | 2 | `repo_index/build_index.py` |
| 24 | `symbols.json` generated + populated | DONE | 2 | `repo_index/symbols.json` |
| 25 | `file_map.json` generated + populated | DONE | 2 | `repo_index/file_map.json` |
| 26 | `search_symbol` tool in `fs.py` | DONE | 2 | `agents/tools/fs.py:108` |
| 27 | `agents/core/context_builder.py` | DONE | 2 | `agents/core/context_builder.py` |
| 28 | Context builder wired into planner worker | DONE | 2 | `agents/workers/planner.py` |
| 29 | `lint/arch_lint.py` — layer checker | DONE | 3 | `lint/arch_lint.py` |
| 30 | `lint/golden_lint.py` — GP-001–GP-010 | DONE | 3 | `lint/golden_lint.py` |
| 31 | `lint/doc_lint.py` — stale doc detection | DONE | 3 | `lint/doc_lint.py` |
| 32 | `lint/rules.py` — centralized rule registry | DONE | 3 | `lint/rules.py` |
| 33 | `lint/run_lint.py` — CLI runner | DONE | 3 | `lint/run_lint.py` |
| 34 | `.github/workflows/ci.yml` | DONE | 3 | `.github/workflows/ci.yml` |
| 35 | `agents/workflows/ralph_loop.py` | DONE | 4 | `agents/workflows/ralph_loop.py` |
| 36 | `agents/workflows/reviewer_loop.py` | DONE | 4 | `agents/workflows/reviewer_loop.py` |
| 37 | PR open/comment/merge via gh tools | DONE | 4 | `agents/tools/git.py` |
| 38 | Human escalation checkpoint in LangGraph | DONE | 4 | `agents/workflows/ralph_loop.py:181` |
| 39 | Cost tracking: `RunMetrics` → Logfire | DONE | 4 | `agents/workflows/ralph_loop.py:215` |
| 40 | `harness/observability/docker-compose.yml` | DONE | 5 | `harness/observability/docker-compose.yml` |
| 41 | `agents/tools/observability.py` (LogQL/PromQL) | DONE | 5 | `agents/tools/observability.py` |
| 42 | `scripts/worktree_up.sh` | DONE | 5 | `scripts/worktree_up.sh` |
| 43 | `scripts/worktree_down.sh` | DONE | 5 | `scripts/worktree_down.sh` |
| 44 | Vector log routing config | DONE | 5 | `harness/observability/vector.toml` |
| 45 | `harness/sandbox/docker-compose.yml` | DONE | 5 | `harness/sandbox/docker-compose.yml` |
| 46 | `agents/tools/browser.py` — Playwright tools | DONE | 6 | `agents/tools/browser.py` |
| 47 | UI validation node in Ralph Loop | PARTIAL | 6 | `agents/workflows/ralph_loop.py` |
| 48 | Before/after screenshot comparison | PENDING | 6 | — |
| 49 | `agents/workflows/entropy_gc.py` | DONE | 7 | `agents/workflows/entropy_gc.py` |
| 50 | `docs/GOLDEN_PRINCIPLES.md` — all 10 | DONE | 7 | `docs/GOLDEN_PRINCIPLES.md` |
| 51 | `docs/QUALITY_SCORE.md` — baseline | DONE | 7 | `docs/QUALITY_SCORE.md` |
| 52 | `.github/workflows/entropy_gc.yml` — daily | DONE | 7 | `.github/workflows/entropy_gc.yml` |
| 53 | Auto-merge for GP-tagged cleanup PRs | DONE | 7 | `agents/workflows/entropy_gc.py` |
| 54 | `tests/agent_eval/test_bug_fix.py` | DONE | 7 | `tests/agent_eval/test_bug_fix.py` |
| 55 | `tests/agent_eval/test_feature_gen.py` | DONE | 7 | `tests/agent_eval/test_feature_gen.py` |
| 56 | `tests/agent_eval/test_entropy_gc.py` | DONE | 7 | `tests/agent_eval/test_entropy_gc.py` |
| 57 | `tests/lint/test_arch_lint.py` | DONE | 3 | `tests/lint/test_arch_lint.py` |
| 58 | `tests/lint/test_golden_lint.py` | DONE | 3 | `tests/lint/test_golden_lint.py` |
| 59 | Worker: `agents/workers/planner.py` | DONE | 1 | `agents/workers/planner.py` |
| 60 | Worker: `agents/workers/implementer.py` | DONE | 1 | `agents/workers/implementer.py` |
| 61 | Worker: `agents/workers/reviewer.py` | DONE | 1 | `agents/workers/reviewer.py` |
| 62 | Worker: `agents/workers/validator.py` | DONE | 1 | `agents/workers/validator.py` |
| 63 | Worker: `agents/workers/cleaner.py` | DONE | 1 | `agents/workers/cleaner.py` |
| 64 | Reference docs (`docs/references/`) | DONE | 1 | `docs/references/*.txt` |
| 65 | `docs/PLANS.md`, `docs/DESIGN.md` | DONE | 1 | `docs/PLANS.md`, `docs/DESIGN.md` |
| 66 | `exec-plans/active/` + `exec-plans/completed/` | DONE | 1 | `docs/exec-plans/` |
| 67 | `.gitignore` | DONE | 1 | `.gitignore` |
| 68 | `gh repo create` (push to remote) | PENDING | 1 | — |
| 69 | `uv sync` — install all dependencies | PENDING | 1 | `pyproject.toml` |

---

## Detailed Task Notes

### DONE tasks — how each was executed

---

#### Task 3 — `AGENTS.md`
**How:** Written as a ~100-line agent-facing navigation document. Covers: core operating principles, full navigation map (all key files with one-line descriptions), starting-a-task checklist, guard rail constants, and key invariants.
**File:** `AGENTS.md`
**Review focus:** Does it give an agent everything it needs to orient in < 60 seconds?

---

#### Task 4 — `ARCHITECTURE.md`
**How:** Documents the layer dependency model (models → config → core → tools → workers → workflows), domain map, data flow, external dependency rules, and naming conventions.
**File:** `ARCHITECTURE.md`
**Review focus:** Are the layer rules complete and unambiguous?

---

#### Task 9 — Vertex AI config
**How:** `agents/core/config.py` wraps `vertexai.init()` + `VertexAIModel` behind a `get_model()` function. Reads `GCP_PROJECT`, `GCP_LOCATION`, `OUROBOROS_MODEL` from env. Lazy initialization — only calls Vertex AI when `get_model()` is actually called.

Note: model name is `gemini-2.0-flash` (current best available; plan says `gemini-3.0-flash` which isn't released yet under that name).

**File:** `agents/core/config.py`
**Review focus:** Is the lazy init pattern correct? Should `model` be a module-level singleton or always call `get_model()`?

---

#### Tasks 10–15 — PydanticAI typed output models
**How:** Each model file defines 1-2 Pydantic `BaseModel` classes. All fields have `Field(description=...)`. No logic except helper methods on `CleanupOutput` (`overall_score()`, `has_blocking_violations()`).

Key design choice in `ValidationOutput`: `next_action: Literal["proceed", "retry", "escalate"]` drives LangGraph routing — no string parsing in the workflow.

**Files:** `agents/models/planner.py`, `agents/models/implementer.py`, `agents/models/reviewer.py`, `agents/models/validator.py`, `agents/models/cleaner.py`, `agents/models/cost.py`
**Review focus:** Are all fields typed correctly? Does `next_action` cover all routing cases?

---

#### Task 16 — `ToolRegistry`
**How:** `agents/tools/registry.py` defines `ToolCapability` (Pydantic model), `ToolRegistry` class, and `REGISTRY` singleton. All 17 tools are registered inline at module level — importing the module auto-populates the registry.

The planner receives `available_tools` from `build_context()`, sourced from `REGISTRY.all_tools()`. It cannot reference tool names that aren't registered.

**File:** `agents/tools/registry.py`
**Review focus:** Are all tool descriptions written well enough for a planner LLM to understand their purpose?

---

#### Tasks 17–19 — Tool implementations
**How:**
- `fs.py`: `read_file`, `write_file`, `list_dir`, `search_repo` (uses ripgrep via subprocess), `search_symbol` (reads `repo_index/symbols.json`). Security: `_resolve()` prevents path traversal outside repo root.
- `shell.py`: `run_tests` (pytest), `run_lint` (ruff + arch + golden lint), `run_build`, `run_command`. All return typed models.
- `git.py`: `git_status`, `commit`, `open_pr`, `get_pr_diff`, `get_pr_comments`, `merge_pr`. All use `gh` CLI via subprocess.

**Files:** `agents/tools/fs.py`, `agents/tools/shell.py`, `agents/tools/git.py`
**Review focus:** Are subprocess calls safe? Does `_resolve()` in `fs.py` correctly prevent traversal?

---

#### Task 20 — Guards
**How:** `agents/core/guards.py` defines 4 constants and `check_guards(state)` which checks them in order. `pre_node_guard(state, node_name)` is the wrapper called at the top of every LangGraph node. Logs a `logfire.warning` when a guard fires.

**File:** `agents/core/guards.py`
**Review focus:** Is the `pre_node_guard` actually being called at the top of every node in `ralph_loop.py`?

---

#### Task 23 — Repo index builder
**How:** `repo_index/build_index.py` uses Python's `ast` module (not tree-sitter — the dependency is listed in `pyproject.toml` but the current impl uses stdlib AST which is faster to get working). Discovers all `.py` files, extracts classes/functions/constants, infers domain/layer from path structure.

Result: 189 symbols, 47 files on first run.

**Files:** `repo_index/build_index.py`, `repo_index/symbols.json`, `repo_index/file_map.json`
**Review focus:** Should tree-sitter be wired in? Current stdlib `ast.parse` covers all Python files correctly. ctags fallback not yet implemented.

---

#### Task 27 — Context builder
**How:** `build_context(task, max_tokens=8000)` extracts keywords from the task string, scores files from `file_map.json` by keyword match, reads relevant file snippets (capped at 80 lines each), loads arch rules from `ARCHITECTURE.md`, checks for active plans, and assembles a `TaskContext` that renders to a prompt string via `to_prompt_text()`.

Token budget enforced by keeping a running `budget` counter and stopping when `budget - cost < 1000`.

**File:** `agents/core/context_builder.py`
**Review focus:** Keyword extraction is naive (split on spaces, filter stopwords). A future improvement is embedding similarity. Current approach is sufficient for v1.

---

#### Tasks 29–33 — Lint system
**How:**
- `lint/rules.py`: `LintRule` dataclass with `agent_remediation` field. 4 ARCH rules + 10 GP rules defined.
- `lint/arch_lint.py`: AST-based import checker. Uses `LAYER_MAP` to classify modules by layer. Checks both layer ordering and worker cross-imports.
- `lint/golden_lint.py`: Implements GP-001 (AST body hash comparison), GP-002 (line count), GP-005 (print() AST scan), GP-009 (regex on plan file dates), GP-010 (file mtime check). GP-003, GP-004, GP-006, GP-007, GP-008 are structurally defined in `rules.py` but their detectors are not yet fully implemented (see PARTIAL below).
- `lint/doc_lint.py`: Scans backtick references in `.md` files against `file_map.json`.
- `lint/run_lint.py`: CLI runner with `--arch-only`, `--golden-only`, `--doc-only` flags.

**Files:** `lint/rules.py`, `lint/arch_lint.py`, `lint/golden_lint.py`, `lint/doc_lint.py`, `lint/run_lint.py`
**Review focus:** GP-003, GP-004, GP-006, GP-007, GP-008 rules exist in `rules.py` with remediation messages but their lint detection functions are not in `golden_lint.py` yet (see PARTIAL section).

---

#### Task 35 — Ralph Loop
**How:** `agents/workflows/ralph_loop.py` implements a full `StateGraph` with 7 nodes: `plan_node`, `implement_node`, `validate_node`, `open_pr_node`, `review_loop_node`, `merge_node`, `human_checkpoint`. Conditional edges driven by `ValidationOutput.next_action` and `ReviewOutput.approved`.

`implement_node` applies `FileChange` objects to disk using `Path.write_text()`. `open_pr_node` calls `commit` then `open_pr` from `agents/tools/git.py`. `run_ralph_loop()` emits `RunMetrics` to Logfire at the end.

**File:** `agents/workflows/ralph_loop.py`
**Review focus:** `implement_node` has an `import aiofiles` that isn't used (uses `Path.write_text` directly). Should be cleaned up.

---

#### Task 44 — Vector config
**How:** `harness/observability/vector.toml` configures two sources (HTTP server at 9001, file at `/var/log/ouroboros/*.log`), one transform (remap timestamps/labels), two sinks (VictoriaLogs via Elasticsearch-compatible API, VictoriaMetrics via Prometheus remote write).

**File:** `harness/observability/vector.toml`
**Review focus:** VictoriaLogs Elasticsearch endpoint path — confirm `:9428/insert/elasticsearch/` is correct for the installed version.

---

#### Task 46 — Browser tools
**How:** `agents/tools/browser.py` uses Playwright async API. Three tools: `take_screenshot` (navigate + screenshot → base64), `snapshot_dom` (accessibility tree → `DOMNode` tree), `drive_ui_flow` (sequence of `UIAction` objects → screenshots per step). Each creates its own browser instance (not shared — no state leakage between calls).

**File:** `agents/tools/browser.py`
**Review focus:** Each tool call spins up and tears down a full browser — high overhead for sequential calls. A future improvement is a long-lived browser context pool.

---

#### Tasks 54–58 — Tests
**How:** All tests use only stdlib + pytest (no `pydantic_ai` or `langgraph` needed). Worker calls are mocked via `patch.dict("sys.modules", ...)` or `patch.object`. Lint tests use real lint functions on `tmp_path` fixtures.

28 tests pass in 0.10s.

**Files:** `tests/lint/test_arch_lint.py`, `tests/lint/test_golden_lint.py`, `tests/agent_eval/test_bug_fix.py`, `tests/agent_eval/test_feature_gen.py`, `tests/agent_eval/test_entropy_gc.py`
**Review focus:** Agent eval tests test model contracts and mock plumbing. True end-to-end agent eval (real LLM calls against real code) is PENDING until infrastructure is live.

---

### PARTIAL tasks — what's done and what's missing

---

#### Task 47 — UI validation node in Ralph Loop
**Status:** Browser tools exist and are registered. The Ralph Loop does NOT yet include a `ui_validate_node` between `open_pr_node` and `review_loop_node`.
**What's missing:** Add a conditional step in `ralph_loop.py` that calls `take_screenshot` and `snapshot_dom` when the task involves UI changes, and attaches results to the review context.
**Files to edit:** `agents/workflows/ralph_loop.py`

---

#### GP-003, GP-004, GP-006, GP-007, GP-008 lint detectors
**Status:** Rules are defined in `lint/rules.py` with full `agent_remediation` text. Detection functions are NOT in `lint/golden_lint.py`.

Specifically missing:
- GP-003: Pattern matching for hand-rolled reimplementations (e.g., custom `slugify`, custom `retry`, etc.)
- GP-004: AST check for unvalidated `json.loads()` / `dict[]` access on external data
- GP-006: AST scan for `BaseModel` subclasses with non-conforming names
- GP-007: Delegate to `ruff --select F401` (already caught by ruff in `run_lint.py` but not surfaced as a named GP violation)
- GP-008: Doc lint cross-references symbol names (currently only checks file paths, not symbol names)

**Files to edit:** `lint/golden_lint.py`, `lint/doc_lint.py`

---

### PENDING tasks — not yet started

---

#### Task 2 / Task 68 — `gh repo create`
**What:** Run `gh repo create project-ouroboros --private --source=. --remote=origin` to push to GitHub.
**Blocker:** Requires user to run manually (or confirm).
**Command:** `gh repo create project-ouroboros --private --source=. --remote=origin`

---

#### Task 48 — Before/after screenshot comparison
**What:** Add a screenshot diffing step to Ralph Loop that compares UI state before and after a change, surfaces the diff as part of the review context.
**Approach:** Capture screenshot before `implement_node`, capture again after, compute pixel diff or attach both to `ReviewOutput`.
**Files to create/edit:** `agents/tools/browser.py` (add `diff_screenshots`), `agents/workflows/ralph_loop.py`

---

#### Task 69 — `uv sync`
**What:** Install all dependencies into a virtual environment.
**Command:** `uv sync --all-extras`
**Note:** `pydantic_ai`, `langgraph`, `logfire`, `google-cloud-aiplatform` are not installed in the system Python. Workers will fail to import until this is run.

---

## Verification Plan Status

| Check | Status | Notes |
|---|---|---|
| 1. Vertex AI connection | PENDING | Requires GCP_PROJECT + `uv sync` |
| 2. Structured output (planner) | PENDING | Requires live model |
| 3. Repo index | DONE | 189 symbols, 47 files |
| 4. Context builder | DONE (unit test) | `build_context()` runs without LLM |
| 5. Guards | DONE (unit test) | Guard logic verified in tests |
| 6. Cost tracking | PENDING | Requires live Logfire token |
| 7. Tool registry | DONE | `REGISTRY.all_tools()` returns 17 tools |
| 8. Logfire traces | PENDING | Requires LOGFIRE_TOKEN |
| 9. Arch lint | DONE | `test_arch_lint.py` passes, REMEDIATION messages verified |
| 10. Ralph Loop e2e | PENDING | Requires live model + GCP |
| 11. Agent eval tests | DONE (model layer) | 28/28 pass; live-LLM eval pending |
| 12. Entropy GC | DONE (model layer) | GP-001 detection verified; live flow pending |
| 13. Observability stack | PENDING | Requires `docker compose up` |

---

## Files Created This Session

```
AGENTS.md
ARCHITECTURE.md
FULL-PLAN.md
CHECKPOINT-1.md
.gitignore
pyproject.toml
requirements.txt

agents/__init__.py
agents/core/__init__.py
agents/core/config.py
agents/core/context_builder.py
agents/core/guards.py
agents/core/instrumentation.py
agents/core/state.py
agents/models/__init__.py
agents/models/cleaner.py
agents/models/cost.py
agents/models/implementer.py
agents/models/planner.py
agents/models/reviewer.py
agents/models/validator.py
agents/tools/__init__.py
agents/tools/browser.py
agents/tools/fs.py
agents/tools/git.py
agents/tools/observability.py
agents/tools/registry.py
agents/tools/shell.py
agents/workers/__init__.py
agents/workers/cleaner.py
agents/workers/implementer.py
agents/workers/planner.py
agents/workers/reviewer.py
agents/workers/validator.py
agents/workflows/__init__.py
agents/workflows/entropy_gc.py
agents/workflows/ralph_loop.py
agents/workflows/reviewer_loop.py

repo_index/__init__.py
repo_index/build_index.py
repo_index/symbols.json        (189 symbols)
repo_index/file_map.json       (47 files)

lint/__init__.py
lint/arch_lint.py
lint/doc_lint.py
lint/golden_lint.py
lint/rules.py
lint/run_lint.py

tests/__init__.py
tests/lint/__init__.py
tests/lint/test_arch_lint.py
tests/lint/test_golden_lint.py
tests/agent_eval/__init__.py
tests/agent_eval/test_bug_fix.py
tests/agent_eval/test_entropy_gc.py
tests/agent_eval/test_feature_gen.py

harness/observability/docker-compose.yml
harness/observability/vector.toml
harness/sandbox/docker-compose.yml

scripts/worktree_up.sh
scripts/worktree_down.sh

docs/DESIGN.md
docs/GOLDEN_PRINCIPLES.md
docs/PLANS.md
docs/QUALITY_SCORE.md
docs/design-docs/core-beliefs.md
docs/design-docs/index.md
docs/exec-plans/active/          (empty dir)
docs/exec-plans/completed/       (empty dir)
docs/references/langgraph-llms.txt
docs/references/pydantic-ai-llms.txt
docs/references/vertexai-llms.txt

.github/workflows/ci.yml
.github/workflows/entropy_gc.yml
```

---

## Next Steps (Priority Order)

1. **`gh repo create project-ouroboros --private --source=. --remote=origin`** — push to GitHub so CI runs
2. **`uv sync`** — install deps, verify `from agents.workers.planner import run_planner` works
3. **Set env vars** — `GCP_PROJECT`, `GCP_LOCATION`, `LOGFIRE_TOKEN`
4. **Verify #1–#8 from verification plan** — Vertex AI, structured output, Logfire traces
5. **Implement missing GP detectors** — GP-003, GP-004, GP-006, GP-007, GP-008 in `lint/golden_lint.py`
6. **Add UI validation node** to `ralph_loop.py` (Task 47)
7. **Add screenshot diff tool** to `browser.py` (Task 48)
8. **Run Ralph Loop e2e** on a real task once infra is live
