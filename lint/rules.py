"""Centralized lint rule registry.

Each rule has an AGENT_REMEDIATION field — the agent reads this and knows exactly
how to fix the violation without human guidance.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class LintRule:
    id: str
    name: str
    description: str
    severity: Literal["error", "warning", "info"]
    agent_remediation: str
    docs_link: str = ""
    auto_fixable: bool = False


ARCH_RULES: list[LintRule] = [
    LintRule(
        id="ARCH-001",
        name="worker-cross-import",
        description="Workers cannot import from other workers.",
        severity="error",
        agent_remediation=(
            "Move the shared logic to agents/core/ or agents/models/. "
            "Import from there in both workers. "
            "See ARCHITECTURE.md#worker-isolation."
        ),
        docs_link="ARCHITECTURE.md#worker-isolation",
    ),
    LintRule(
        id="ARCH-002",
        name="tool-imports-worker",
        description="Tools cannot import from workers. Tools are stateless utilities.",
        severity="error",
        agent_remediation=(
            "Remove the worker import from the tool. "
            "Tools call functions, not workers. "
            "If you need worker output types, import from agents/models/ instead."
        ),
        docs_link="ARCHITECTURE.md#layer-dependency-rules",
    ),
    LintRule(
        id="ARCH-003",
        name="model-imports-worker",
        description="Model files cannot import from workers, tools, or workflows.",
        severity="error",
        agent_remediation=(
            "agents/models/ files define output types only. "
            "They may only import from stdlib and pydantic. "
            "Move any logic to the appropriate worker or tool."
        ),
        docs_link="ARCHITECTURE.md#layer-dependency-rules",
    ),
    LintRule(
        id="ARCH-004",
        name="workflow-bypasses-worker",
        description="Workflows must call workers, not directly call tools or models.",
        severity="warning",
        agent_remediation=(
            "Route the tool call through the appropriate worker. "
            "Workflows orchestrate workers; workers orchestrate tools."
        ),
        docs_link="ARCHITECTURE.md#data-flow",
    ),
]

GOLDEN_RULES: list[LintRule] = [
    LintRule(
        id="GP-001",
        name="no-duplicate-utilities",
        description="No duplicate utility functions across packages.",
        severity="error",
        agent_remediation=(
            "Deduplicate by moving the canonical implementation to agents/core/ or a shared module. "
            "Update all import sites. Use search_symbol() to find all references before removing."
        ),
        auto_fixable=True,
    ),
    LintRule(
        id="GP-002",
        name="no-file-exceeds-500-lines",
        description="No Python file may exceed 500 lines.",
        severity="warning",
        agent_remediation=(
            "Split the file into logical sub-modules. "
            "Create a new module for each coherent group of functions/classes. "
            "Update __init__.py if needed."
        ),
    ),
    LintRule(
        id="GP-003",
        name="no-hand-rolled-duplicates",
        description="No hand-rolled helpers duplicating shared packages.",
        severity="warning",
        agent_remediation=(
            "Replace with the appropriate library call. Check pyproject.toml for available packages. "
            "Remove the custom helper after confirming no other callers."
        ),
    ),
    LintRule(
        id="GP-004",
        name="external-data-validated",
        description="All external data must be validated through Pydantic models.",
        severity="error",
        agent_remediation=(
            "Wrap the external data access in a Pydantic model parse. "
            "Create a *Schema model if one doesn't exist. "
            "Pattern: MyModel.model_validate(raw_data)"
        ),
    ),
    LintRule(
        id="GP-005",
        name="no-print-outside-scripts",
        description="No print() calls outside scripts/.",
        severity="info",
        agent_remediation=(
            "Replace print() with logfire.info(message, **context_kwargs). "
            "Import logfire at the top of the file."
        ),
        auto_fixable=True,
    ),
    LintRule(
        id="GP-006",
        name="schema-naming-convention",
        description="Pydantic models must use *Output, *Result, or *Schema naming.",
        severity="info",
        agent_remediation=(
            "Rename the model to follow the convention. "
            "Use search_symbol() to find all references. "
            "Update all import sites and type annotations."
        ),
    ),
    LintRule(
        id="GP-007",
        name="no-dead-imports",
        description="All imports must be used.",
        severity="info",
        agent_remediation=(
            "Run: python -m ruff check --fix --select F401 <file> "
            "ruff will auto-remove unused imports."
        ),
        auto_fixable=True,
    ),
    LintRule(
        id="GP-008",
        name="docs-reference-real-code",
        description="All file paths and symbols in docs must exist in the repo.",
        severity="warning",
        agent_remediation=(
            "Update the documentation to reference the current file/symbol location. "
            "Use search_symbol() or the file_map to find the current location."
        ),
    ),
    LintRule(
        id="GP-009",
        name="active-plans-current",
        description="Active plans must be updated within 7 days.",
        severity="warning",
        agent_remediation=(
            "Open the stale plan and update 'Last Updated' date. "
            "Mark completed steps with [x]. "
            "If the plan is done, move it to docs/exec-plans/completed/."
        ),
    ),
    LintRule(
        id="GP-010",
        name="quality-score-current",
        description="QUALITY_SCORE.md must be updated within 24 hours.",
        severity="info",
        agent_remediation=("Run: python agents/workflows/entropy_gc.py --update-scores-only"),
        auto_fixable=True,
    ),
]

WORKFLOW_RULES: list[LintRule] = [
    LintRule(
        id="WF-001",
        name="node-must-guard",
        description="Every workflow node must call pre_node_guard() at entry.",
        severity="error",
        agent_remediation=(
            "Add `guard = pre_node_guard(state, 'node_name')` as the first line "
            "of the node function, followed by "
            "`if not guard.allowed: return {'status': 'escalated', "
            "'error_log': state['error_log'] + [guard.reason]}`."
        ),
        docs_link="agents/core/guards.py",
    ),
    LintRule(
        id="WF-002",
        name="node-return-tracking",
        description=(
            "Every non-guard-failure return from a workflow node must include "
            "total_tool_calls and node_tool_calls tracking keys."
        ),
        severity="error",
        agent_remediation=(
            "Add 'total_tool_calls': state['total_tool_calls'] + N and "
            "'node_tool_calls': update_node_tool_calls(state, 'node_name', N) "
            "to the return dict. Use accumulate_usage() for LLM nodes."
        ),
        docs_link="agents/core/workflow_helpers.py",
    ),
    LintRule(
        id="WF-003",
        name="context-role-mismatch",
        description=(
            "build_context(worker_role=X) result must be passed to run_X(), "
            "not to a different worker's runner."
        ),
        severity="error",
        agent_remediation=(
            "Build separate contexts for each worker: "
            "planner_ctx = build_context(task, worker_role='planner') and "
            "impl_ctx = build_context(task, worker_role='implementer'). "
            "Pass each to the matching run_*() function."
        ),
        docs_link="agents/core/context_builder.py",
    ),
    LintRule(
        id="WF-004",
        name="guard-exemption-requires-listing",
        description=(
            "Guard-exempt nodes must be listed in _EXEMPT_NODES with a reason. "
            "A node without pre_node_guard() that is NOT in _EXEMPT_NODES is a violation."
        ),
        severity="error",
        agent_remediation=(
            "Either add the guard call, or add the node name to _EXEMPT_NODES in "
            "lint/workflow_lint.py with a comment explaining why it is exempt."
        ),
        docs_link="lint/workflow_lint.py",
    ),
    LintRule(
        id="WF-005",
        name="status-aware-edges",
        description=(
            "Nodes that can return status='failed' or status='escalated' must use "
            "add_conditional_edges, not add_edge. A fixed edge silently continues "
            "after a guard/error path."
        ),
        severity="error",
        agent_remediation=(
            "Replace graph.add_edge(node, next) with "
            "graph.add_conditional_edges(node, route_fn) where route_fn checks "
            "state['status'] and routes to END or human_checkpoint on failure."
        ),
        docs_link="agents/workflows/ralph_routing.py",
    ),
    LintRule(
        id="WF-006",
        name="loop-tool-call-accounting",
        description=(
            "Tool calls inside for/while loops must use an attempt counter that "
            "feeds into both total_tool_calls and node_tool_calls. Counting only "
            "successes understates the budget."
        ),
        severity="warning",
        agent_remediation=(
            "Add an `attempts` counter incremented on every loop iteration, "
            "regardless of success/failure. Use `attempts` (not `succeeded`) "
            "for total_tool_calls and node_tool_calls updates."
        ),
    ),
    LintRule(
        id="WF-007",
        name="budget-off-by-one",
        description=(
            "Post-call >= MAX_TOOL_CALLS_PER_NODE patterns turn the last allowed "
            "call into a failure. Use > for post-call checks, or >= for pre-call."
        ),
        severity="warning",
        agent_remediation=(
            "Change the post-call check from `>= MAX_TOOL_CALLS_PER_NODE` to "
            "`> MAX_TOOL_CALLS_PER_NODE`, or move the check before the call."
        ),
    ),
    LintRule(
        id="WF-009",
        name="llm-node-must-accumulate-usage",
        description=(
            "Nodes calling run_planner, run_implementer, run_reviewer, or "
            "run_post_mortem must use accumulate_usage() in the return path."
        ),
        severity="warning",
        agent_remediation=(
            "Add **accumulate_usage(state, usage, 'node_name', tool_calls=N) "
            "to the return dict, and ensure the usage variable from the "
            "run_*() call is passed through."
        ),
        docs_link="agents/core/workflow_helpers.py",
    ),
    LintRule(
        id="WF-010",
        name="no-direct-file-mutation-in-workflows",
        description=(
            "Workflow nodes must not call Path.write_text, unlink, mkdir, etc. "
            "directly. Use apply_file_changes() or a registered tool."
        ),
        severity="warning",
        agent_remediation=(
            "Replace direct Path mutations with apply_file_changes() for "
            "file writes, or use a tool from agents/tools/. "
            "This prevents duplicated mutation logic across workflows."
        ),
    ),
]

GOLDEN_RULES_EXTENDED: list[LintRule] = [
    LintRule(
        id="GP-011",
        name="no-cross-module-private-imports",
        description="Do not import _-prefixed names from other modules.",
        severity="warning",
        agent_remediation=(
            "Rename the private function/variable to a public name (remove _ prefix) "
            "if it is intended to be part of the module's API. "
            "If it must stay private, extract a public wrapper."
        ),
    ),
    LintRule(
        id="GP-012",
        name="file-encoding",
        description=("All file I/O (.read_text, .write_text, open) must specify encoding='utf-8'."),
        severity="warning",
        agent_remediation=(
            "Add encoding='utf-8' as a keyword argument to the file I/O call. "
            "For open(), add encoding='utf-8'. "
            "For .read_text()/.write_text(), add encoding='utf-8'."
        ),
        auto_fixable=True,
    ),
    LintRule(
        id="GP-013",
        name="no-silent-exception-swallow",
        description=(
            "except Exception handlers must not silently swallow errors "
            "(return {} or pass without error propagation)."
        ),
        severity="error",
        agent_remediation=(
            "Add error propagation to the except handler: either re-raise, "
            "append to error_log, or return a dict with 'error_log' or 'status' key. "
            "Logging alone is not enough — the caller must know the operation failed."
        ),
    ),
    LintRule(
        id="GP-014",
        name="no-hardcoded-guard-limits",
        description=(
            "Guard limits in workflow code must use constants from agents.core.guards, "
            "not magic numbers."
        ),
        severity="error",
        agent_remediation=(
            "Import the appropriate constant from agents.core.guards "
            "(MAX_IMPLEMENT_ITERATIONS, MAX_REVIEW_ITERATIONS, MAX_TOOL_CALLS_PER_NODE, "
            "MAX_TOTAL_TOOL_CALLS) and use it instead of the hardcoded number."
        ),
    ),
]

ALL_RULES: list[LintRule] = ARCH_RULES + GOLDEN_RULES + WORKFLOW_RULES + GOLDEN_RULES_EXTENDED
RULES_BY_ID: dict[str, LintRule] = {r.id: r for r in ALL_RULES}
