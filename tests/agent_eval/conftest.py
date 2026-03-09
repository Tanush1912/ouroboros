"""Shared test fixtures for agent_eval tests."""

from agents.core.state import initial_state


def _state_with(**overrides):
    """Build a RalphState from initial_state with overrides applied."""
    state = initial_state("test task")
    state.update(overrides)
    return state


def make_reviewer_state(**overrides) -> dict:
    """Minimal ReviewerState-like dict for guard/routing testing."""
    base = {
        "pr_number": 1,
        "task": "test task",
        "review": None,
        "review_iteration_count": 0,
        "resolved": False,
        "status": "reviewing",
        "error_log": [],
        "estimated_cost_usd": 0.0,
        "cost_budget_usd": 2.0,
        "total_tool_calls": 0,
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "node_tool_calls": {},
        "node_token_usage": {},
    }
    base.update(overrides)
    return base


def make_feedback_state(**overrides) -> dict:
    """Minimal FeedbackState-like dict for guard/routing testing."""
    base = {
        "pr_number": 1,
        "pr_branch": "fix/test",
        "original_task": "test task",
        "feedback_comments": [],
        "files_changed": [],
        "validation": None,
        "iteration_count": 0,
        "status": "idle",
        "error_log": [],
        "total_tokens_in": 0,
        "total_tokens_out": 0,
        "estimated_cost_usd": 0.0,
        "cost_budget_usd": 2.0,
        "total_tool_calls": 0,
        "node_token_usage": {},
        "node_tool_calls": {},
    }
    base.update(overrides)
    return base
