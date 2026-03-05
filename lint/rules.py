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

ALL_RULES: list[LintRule] = ARCH_RULES + GOLDEN_RULES
RULES_BY_ID: dict[str, LintRule] = {r.id: r for r in ALL_RULES}
