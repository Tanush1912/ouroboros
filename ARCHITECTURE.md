# ARCHITECTURE.md — Domain/Layer Map

## Layer Dependency Rules

Layers are ordered. Each layer may only import from layers below it.

```
models → config → core → tools → workers → workflows → cli/scripts
```

Cross-cutting concerns (logging, metrics, auth) enter only via `agents/core/`.

### Enforced by `lint/arch_lint.py`

| Layer | Module Prefix | May Import From |
|---|---|---|
| models | `agents.models.*` | stdlib, pydantic |
| config | `agents.core.config` | `agents.models.*`, stdlib |
| core | `agents.core.*` | `agents.models.*`, `agents.core.config` |
| tools | `agents.tools.*` | `agents.models.*`, `agents.core.*` |
| workers | `agents.workers.*` | `agents.models.*`, `agents.core.*`, `agents.tools.*` |
| workflows | `agents.workflows.*` | everything above |

### Violations

Workers **cannot** cross-import each other. If two workers share logic, extract to `agents/core/`.
Tools **cannot** import workers. Tools are stateless utilities; workers orchestrate them.

### Documented Exceptions

Workflows may import directly from `agents.tools.*` for **infrastructure operations** — git commits, PR creation, merges, and lint execution. These are mechanical side-effects (no LLM reasoning), so routing them through worker wrappers would add indirection without value. Agent reasoning must always go through workers.

---

## Domain Map

```
project-ouroboros/
├── agents/          Domain: agent system
│   ├── core/        Layer: core infrastructure (guards, context, state)
│   ├── models/      Layer: typed output schemas
│   ├── workers/     Layer: PydanticAI agent implementations
│   ├── tools/       Layer: tool functions + registry
│   └── workflows/   Layer: LangGraph workflow definitions
│
├── lint/            Domain: code quality enforcement
├── repo_index/      Domain: repository symbol index
├── tests/           Domain: verification
├── harness/         Domain: infrastructure (Docker stacks)
└── scripts/         Domain: operational scripts (CLI entrypoints)
```

---

## Data Flow

```
Task (str)
  → build_context()           # context_builder.py — scoped, budgeted
  → PlannerWorker             # returns PlanOutput (typed)
  → ImplementerWorker         # returns ImplementOutput (typed)
  → ValidatorWorker           # returns ValidationOutput (typed)
  → [conditional routing]     # driven by ValidationOutput.next_action
  → ReviewerWorker            # returns ReviewOutput (typed)
  → [conditional routing]     # driven by ReviewOutput.approved
  → git tools (open_pr, merge)
  → RunMetrics → Logfire
```

No step produces raw text. Every handoff is a typed Pydantic model.

---

## Observability Architecture

```
Agent code → Logfire (OTel)
App code   → Vector → VictoriaLogs / VictoriaMetrics → Grafana
                                                      → Agent query tools (LogQL/PromQL)
```

Agents can query their own observability stack via `agents/tools/observability.py`.

---

## External Dependency Rules

- Vertex AI accessed only through `agents/core/config.py`
- GitHub CLI (`gh`) called only through `agents/tools/git.py`
- Playwright accessed only through `agents/tools/browser.py`
- Docker accessed only through `scripts/worktree_up.sh` / `worktree_down.sh`

---

## Naming Conventions

- Output models: `*Output` suffix (e.g., `PlanOutput`, `ReviewOutput`)
- Result models: `*Result` suffix (e.g., `TestResult`, `CommitResult`)
- Workers: `*Worker` class + `run_*` function (e.g., `PlannerWorker`, `run_planner`)
- Tools: snake_case verb_noun (e.g., `read_file`, `run_tests`, `open_pr`)
- LangGraph nodes: `*_node` suffix (e.g., `plan_node`, `validate_node`)
