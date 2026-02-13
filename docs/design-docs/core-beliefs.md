# Core Beliefs — Agent-First Operating Principles

## 1. Structure Over Text

Agents communicate through Pydantic models, not strings. Every boundary between agents,
between tools, and between workflow nodes carries a typed contract. "Parse the LLM's output"
is a code smell — if it can fail silently, it will.

## 2. The Planner Is Not Omniscient

The planner's job is to produce a `PlanOutput` that is executable given the available tools.
It must query `REGISTRY.all_tools()` before planning. If a tool doesn't exist in the registry,
it cannot be in the plan. Hallucinated tool names are caught at plan validation time.

## 3. Token Budget Is a First-Class Concern

Context windows are finite. `build_context()` enforces a token budget. Agents that read
whole files "just in case" are agents that fail on large repos. Use `search_symbol()` to find
specific code, not `read_file("everything.py")`.

## 4. Guards Are Not Suggestions

`MAX_IMPLEMENT_ITERATIONS = 5` is a hard constant. It is not configurable at runtime.
An agent that loops forever is worse than an agent that escalates. When in doubt, escalate.
The human checkpoint exists precisely for cases where the agent cannot proceed.

## 5. The Repo Index Is the Map

The repo index (`symbols.json`, `file_map.json`) is the agent's map of the codebase.
Keep it current. Run `build_index.py` after significant changes. An agent navigating without
the index is walking blind.

## 6. Entropy Accumulates Without Active Countermeasures

Code entropy is not a one-time problem. It accumulates continuously. The GC workflow is
a daily investment that prevents entropy from compounding. A small cleanup PR opened today
prevents a large refactor required next month.

## 7. Every Run Has a Cost

Every agent run consumes tokens, time, and money. `CostSummary` is not a vanity metric —
it is a regression signal. A task that costs 2x more than last week is a signal that something
changed (model, prompt, context, or problem complexity). Track it in Logfire.

## 8. The Self-Referential Loop Is the Feature

Ouroboros can be tasked to improve itself. The agent workers can write better agent workers.
The lint rules can be improved by agents. This is not a risk — it is the point.
The only constraint is that self-modification must go through the same PR review process
as any other change.

## 9. Observability Is a Tool, Not an Afterthought

Agents can query logs and metrics via `query_logs()` and `query_metrics()`. This means
agents can diagnose production issues the same way humans do — by querying the observability
stack. An agent that can see its own behavior is an agent that can improve.

## 10. Small, Atomic, Reversible

Prefer 10 small PRs over 1 large PR. Atomic PRs are reviewable, mergeable, and revertable.
The GC workflow opens one PR per principle violation cluster. The Ralph Loop opens one PR
per task. Large PRs indicate a task was scoped too broadly — split it.
