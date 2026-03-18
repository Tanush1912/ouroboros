"""Ralph Loop routing functions — adaptive, planner-controlled pipeline.

The planner sets skip_stages on PlanOutput to control which workflow stages
run. Routing functions use _should_skip() and _next_stage() to navigate
the pipeline dynamically instead of following a rigid path.
"""

from langgraph.graph import END

from agents.core.guards import MAX_REVIEW_ITERATIONS, MAX_TEST_WRITER_ITERATIONS
from agents.core.state import RalphState

_BUG_FIX_KEYWORDS = frozenset({"fix", "bug", "error", "broken", "failing", "crash"})

# Ordered post-validation stages. Routing uses this to find the next
# non-skipped stage after a given point.
_POST_VALIDATE_STAGES = [
    "mutation",
    "perf_validate",
    "ui_validate",
    "open_pr",
    "review",
    "merge",
]

_STAGE_TO_NODE = {
    "mutation": "mutation_validate_node",
    "perf_validate": "perf_validate_node",
    "ui_validate": "ui_validate_node",
    "open_pr": "open_pr_node",
    "review": "review_loop_node",
    "merge": "merge_node",
}


def _should_skip(state: RalphState, stage: str) -> bool:
    """Check if a stage should be skipped based on the planner's skip_stages."""
    plan = state.get("plan")
    if plan is None:
        return False
    return stage in plan.skip_stages


def _resolve_next_stage(state: RalphState, after: str) -> str:
    """Find the next non-skipped node after the given stage.

    Walks _POST_VALIDATE_STAGES starting after `after`, skipping any stage
    in plan.skip_stages. Returns the corresponding node name, or END if
    all remaining stages are skipped.
    """
    plan = state.get("plan")
    skip = set(plan.skip_stages) if plan else set()
    try:
        idx = _POST_VALIDATE_STAGES.index(after) + 1
    except ValueError:
        idx = 0
    while idx < len(_POST_VALIDATE_STAGES):
        stage = _POST_VALIDATE_STAGES[idx]
        if stage not in skip:
            return _STAGE_TO_NODE[stage]
        idx += 1
    return END


# --- Routing functions ---


def route_after_plan(state: RalphState) -> str:
    """Route to reproduce_node for bug-fix tasks, otherwise straight to implement."""
    if state["status"] == "escalated":
        return "human_checkpoint"

    # Planner can skip reproduction, but bug-fix keywords override
    if not _should_skip(state, "reproduce"):
        has_prior_failure = state["validation"] is not None and not state["validation"].overall_pass
        task_lower = state["task"].lower()
        has_bug_keywords = any(kw in task_lower for kw in _BUG_FIX_KEYWORDS)
        if has_prior_failure or has_bug_keywords:
            return "reproduce_node"

    return "implement_node"


def _test_failures_in_test_files(failures: list[str]) -> bool:
    """Check if test failures reference test files (test_writer's fault)."""
    return any("test_" in f and ("FAILED" in f or "Error" in f) for f in failures)


def route_after_reproduce(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return "implement_node"


def route_after_implement(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    if _should_skip(state, "test_writer"):
        return "validate_node"
    return "test_writer_node"


def route_after_test_writer(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return "validate_node"


def route_after_validate(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    validation = state["validation"]
    if validation is None:
        return "human_checkpoint"

    if validation.next_action == "proceed":
        return _resolve_next_stage(state, "validate")
    if validation.next_action == "escalate":
        return "human_checkpoint"

    # Retry — determine if it's a test quality issue or a code issue
    quality = validation.test_quality
    tests_pass = validation.tests.passed
    test_writer_maxed = state.get("test_writer_iteration", 0) >= MAX_TEST_WRITER_ITERATIONS

    # Tests pass but quality is bad → test writer
    if tests_pass and quality is not None and not quality.passed:
        if test_writer_maxed or _should_skip(state, "test_writer"):
            return "human_checkpoint"
        return "test_writer_node"

    # Tests failed in test files → test writer wrote broken tests
    if not tests_pass and _test_failures_in_test_files(validation.tests.failures):
        if test_writer_maxed or _should_skip(state, "test_writer"):
            return "human_checkpoint"
        return "test_writer_node"

    # Production code bugs or lint failures → implementer
    return "implement_node"


def route_after_mutation(state: RalphState) -> str:
    """Route after mutation sampling. Low kill rate → test writer for retry."""
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    mutation = state.get("mutation_result")
    if mutation is not None and not mutation.passed:
        if state.get("test_writer_iteration", 0) >= MAX_TEST_WRITER_ITERATIONS:
            return "human_checkpoint"
        return "test_writer_node"
    return _resolve_next_stage(state, "mutation")


def route_after_perf_validate(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return _resolve_next_stage(state, "perf_validate")


def route_after_ui_validate(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return _resolve_next_stage(state, "ui_validate")


def route_after_open_pr(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return _resolve_next_stage(state, "open_pr")


def route_after_review(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    review = state["review"]
    if review is None or not review.approved or not review.has_meaningful_tests:
        if state["review_iteration_count"] >= MAX_REVIEW_ITERATIONS:
            return "human_checkpoint"
        return "implement_node"
    return "merge_node"


def route_after_merge(state: RalphState) -> str:
    if state.get("status") in ("failed", "escalated"):
        return "human_checkpoint"
    return END
