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
        status="planning",
        error_log=[],
    )
