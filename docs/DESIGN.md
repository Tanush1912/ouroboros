# System Design — Project Ouroboros

## Vision

An agent-first software factory where the primary interface is natural language tasks,
and the output is merged, tested, reviewed pull requests.

The system is self-referential: agents can be tasked to improve the agent infrastructure itself.

## Core Design Decisions

### Why PydanticAI?
Typed structured outputs at every agent boundary. No prompt parsing, no regex, no JSON
extraction. Every handoff between agents is a Python type that mypy can verify.

### Why LangGraph?
Explicit state machine. Conditional routing driven by typed fields (`next_action`, `approved`).
Built-in human escalation checkpoints. Reproducible — state is serializable.

### Why Logfire?
First-class PydanticAI instrumentation. Zero-config tracing of all agent calls.
OTel native — same pipeline as app observability. Pydantic models surface as structured spans.

### Why Vertex AI?
Production-grade rate limits for high-throughput agent runs. IAM-based auth (no key rotation).
Regional isolation. Usage quotas per project.

## Key Design Patterns

### Context Builder Pattern
Agents never receive raw file dumps. `build_context(task)` produces a `TaskContext` with
a token budget enforced before the agent sees anything. Prevents context poisoning.

### Tool Registry Pattern
Planner queries `REGISTRY.all_tools()` before making a plan. Cannot hallucinate tool names.
When a tool is added to the registry, planner capabilities update automatically.

### Guard Rail Pattern
Hard iteration and tool-call limits enforced at every LangGraph node via `check_guards()`.
Constants, not config — not tunable at runtime. When limits hit → escalate, don't retry.

### Entropy GC Pattern
Entropy is tracked as a first-class concern. Golden Principles (GP-001 to GP-010) are
machine-checkable rules. Daily GC workflow opens tiny, atomic cleanup PRs. Quality scores
are auto-updated and human-readable.
