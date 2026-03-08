"""LangGraph typed state schema for the Ralph Loop workflow."""

from typing import Literal, TypedDict

from agents.models.benchmark import BenchmarkResult, PerfComparisonResult
from agents.models.implementer import FileChange
from agents.models.planner import PlanOutput
from agents.models.reproducer import ReproductionResult
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
    total_tokens_in: int
    total_tokens_out: int
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
    ui_screenshots: list[str]
    node_token_usage: dict[str, dict[str, int]]
    reproduction_evidence: ReproductionResult | None
    perf_baseline: BenchmarkResult | None
    perf_result: PerfComparisonResult | None


class FeedbackState(TypedDict):
    pr_number: int
    pr_branch: str
    original_task: str
    feedback_comments: list[dict[str, object]]
    files_changed: list[FileChange]
    validation: ValidationOutput | None
    iteration_count: int
    total_tokens_in: int
    total_tokens_out: int
    estimated_cost_usd: float
    cost_budget_usd: float
    total_tool_calls: int
    status: Literal[
        "gathering",
        "implementing",
        "validating",
        "pushing",
        "replying",
        "done",
        "escalated",
        "failed",
    ]
    error_log: list[str]
    node_token_usage: dict[str, dict[str, int]]


def initial_feedback_state(
    pr_number: int,
    pr_branch: str,
    original_task: str,
    feedback_comments: list[dict],
) -> FeedbackState:
    """Create a fresh initial state for a feedback loop run."""
    return FeedbackState(
        pr_number=pr_number,
        pr_branch=pr_branch,
        original_task=original_task,
        feedback_comments=feedback_comments,
        files_changed=[],
        validation=None,
        iteration_count=0,
        total_tokens_in=0,
        total_tokens_out=0,
        estimated_cost_usd=0.0,
        cost_budget_usd=2.0,
        total_tool_calls=0,
        status="gathering",
        error_log=[],
        node_token_usage={},
    )


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
        total_tokens_in=0,
        total_tokens_out=0,
        estimated_cost_usd=0.0,
        cost_budget_usd=2.0,
        status="planning",
        error_log=[],
        ui_screenshots=[],
        node_token_usage={},
        reproduction_evidence=None,
        perf_baseline=None,
        perf_result=None,
    )
