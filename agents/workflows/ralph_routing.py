"""Ralph Loop routing functions — status-aware conditional edges.

Extracted from ralph_loop.py to stay under GP-002 (500 lines).
Each function checks state["status"] and routes to human_checkpoint
on failure/escalation.
"""

from langgraph.graph import END

from agents.core.guards import MAX_REVIEW_ITERATIONS, MAX_TEST_WRITER_ITERATIONS
from agents.core.state import RalphState

_BUG_FIX_KEYWORDS = frozenset({"fix", "bug", "error", "broken", "failing", "crash"})


def route_after_plan(state: RalphState) -> str:
    """Route to reproduce_node for bug-fix tasks, otherwise straight to implement."""
    if state["status"] == "escalated":
        return "human_checkpoint"

    has_prior_failure = state["validation"] is not None and not state["validation"].overall_pass
    task_lower = state["task"].lower()
    has_bug_keywords = any(kw in task_lower for kw in _BUG_FIX_KEYWORDS)

    if has_prior_failure or has_bug_keywords:
        return "reproduce_node"
    return "implement_node"


def _test_failures_in_test_files(failures: list[str]) -> bool:
    """Check if test failures reference test files (test_writer's fault, not implementer's)."""
    return any("test_" in f and ("FAILED" in f or "Error" in f) for f in failures)


def route_after_validate(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    validation = state["validation"]
    if validation is None:
        return "human_checkpoint"

    if validation.next_action == "proceed":
        return "mutation_validate_node"
    if validation.next_action == "escalate":
        return "human_checkpoint"

    # Retry — determine if it's a test quality issue or a code issue
    quality = validation.test_quality
    tests_pass = validation.tests.passed
    test_writer_maxed = state.get("test_writer_iteration", 0) >= MAX_TEST_WRITER_ITERATIONS

    # Tests pass but quality is bad → test writer
    if tests_pass and quality is not None and not quality.passed:
        if test_writer_maxed:
            return "human_checkpoint"
        return "test_writer_node"

    # Tests failed in test files → test writer wrote broken tests
    if not tests_pass and _test_failures_in_test_files(validation.tests.failures):
        if test_writer_maxed:
            return "human_checkpoint"
        return "test_writer_node"

    # Production code bugs or lint failures → implementer
    return "implement_node"


def route_after_review(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    review = state["review"]
    if review is None or not review.approved or not review.has_meaningful_tests:
        if state["review_iteration_count"] >= MAX_REVIEW_ITERATIONS:
            return "human_checkpoint"
        return "implement_node"
    return "merge_node"


def _ralph_status_gate(state: RalphState, next_node: str) -> str:
    """Route to human_checkpoint on failure/escalation, otherwise continue."""
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return next_node


def route_after_implement(state: RalphState) -> str:
    return _ralph_status_gate(state, "test_writer_node")


def route_after_test_writer(state: RalphState) -> str:
    return _ralph_status_gate(state, "validate_node")


def route_after_reproduce(state: RalphState) -> str:
    return _ralph_status_gate(state, "implement_node")


def route_after_mutation(state: RalphState) -> str:
    """Route after mutation sampling. Low kill rate → test writer for retry."""
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    mutation = state.get("mutation_result")
    if mutation is not None and not mutation.passed:
        if state.get("test_writer_iteration", 0) >= MAX_TEST_WRITER_ITERATIONS:
            return "human_checkpoint"
        return "test_writer_node"
    return "perf_validate_node"


def route_after_perf_validate(state: RalphState) -> str:
    return _ralph_status_gate(state, "ui_validate_node")


def route_after_ui_validate(state: RalphState) -> str:
    return _ralph_status_gate(state, "open_pr_node")


def route_after_open_pr(state: RalphState) -> str:
    return _ralph_status_gate(state, "review_loop_node")


def route_after_merge(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return END
