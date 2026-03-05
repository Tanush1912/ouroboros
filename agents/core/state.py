"""LangGraph typed state schema for the Ralph Loop workflow."""

from typing import Literal, TypedDict

from agents.models.implementer import FileChange
from agents.models.planner import PlanOutput
from agents.models.reviewer import ReviewOutput
from agents.models.validator import ValidationOutput


class RalphState(TypedDict):
    task: str
    plan: PlanOutput | None
    files_changed: list[FileChange]
    validation: ValidationOutput | None
    review: ReviewOutput | None
    pr_url: str | None
    pr_number: int | None
    iteration_count: int
    review_iteration_count: int
    total_tool_calls: int
    estimated_cost_usd: float
    cost_budget_usd: float
    status: Literal[
        "planning",
        "implementing",
        "validating",
        "reviewing",
        "merging",
        "done",
        "escalated",
        "failed",
    ]
    error_log: list[str]
    ui_screenshots: list[str]  # Base64 screenshots from ui_validate_node (empty if not a UI task)


def initial_state(task: str) -> RalphState:
    """Create a fresh initial state for a new Ralph Loop run."""
    return RalphState(
        task=task,
        plan=None,
        files_changed=[],
        validation=None,
        review=None,
        pr_url=None,
        pr_number=None,
        iteration_count=0,
        review_iteration_count=0,
        total_tool_calls=0,
        estimated_cost_usd=0.0,
        cost_budget_usd=2.0,
        status="planning",
        error_log=[],
        ui_screenshots=[],
    )
