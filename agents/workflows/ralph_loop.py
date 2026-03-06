"""Ralph Loop — main PR lifecycle LangGraph workflow.

State machine:
  start → plan_node → implement_node → validate_node
         → [retry] → implement_node (max 5)
         → [escalate] → human_checkpoint
         → [proceed] → ui_validate_node → open_pr_node → review_loop_node
         → [not approved] → implement_node (address feedback)
         → [approved] → merge_node → done
"""

import os
import time
from typing import Any

import logfire
from langgraph.graph import END, StateGraph

from agents.core.context_builder import build_context
from agents.core.guards import pre_node_guard
from agents.core.state import RalphState, initial_state
from agents.models.benchmark import PerfComparisonResult
from agents.models.cost import CostSummary, RunMetrics, TokenUsage
from agents.models.reproducer import ErrorContext, ReproductionResult
from agents.tools.git import commit, merge_pr, open_pr
from agents.workers.implementer import run_implementer
from agents.workers.planner import run_planner
from agents.workers.reviewer import run_reviewer
from agents.workers.validator import run_validator


def _accumulate_usage(state: RalphState, usage: TokenUsage, node_name: str) -> dict:
    """Return state updates for token/cost accumulation, including per-node tracking."""
    prev = state["node_token_usage"].get(node_name, {"tokens_in": 0, "tokens_out": 0})
    updated_node_usage = dict(state["node_token_usage"])
    updated_node_usage[node_name] = {
        "tokens_in": prev["tokens_in"] + usage.tokens_in,
        "tokens_out": prev["tokens_out"] + usage.tokens_out,
    }
    return {
        "total_tokens_in": state["total_tokens_in"] + usage.tokens_in,
        "total_tokens_out": state["total_tokens_out"] + usage.tokens_out,
        "estimated_cost_usd": state["estimated_cost_usd"] + usage.cost_usd(),
        "node_token_usage": updated_node_usage,
    }


async def plan_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "plan_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    context = build_context(state["task"])
    plan, usage = await run_planner(state["task"], context)
    return {
        "plan": plan,
        "status": "implementing",
        **_accumulate_usage(state, usage, "plan_node"),
        "total_tool_calls": state["total_tool_calls"] + 1,
    }


_BUG_FIX_KEYWORDS = {"fix", "bug", "error", "broken", "failing", "crash"}


def route_after_plan(state: RalphState) -> str:
    """Route to reproduce_node for bug-fix tasks, otherwise straight to implement."""
    if state["status"] == "escalated":
        return "implement_node"

    has_prior_failure = state["validation"] is not None and not state["validation"].overall_pass
    task_lower = state["task"].lower()
    has_bug_keywords = any(kw in task_lower for kw in _BUG_FIX_KEYWORDS)

    if has_prior_failure or has_bug_keywords:
        return "reproduce_node"
    return "implement_node"


async def reproduce_node(state: RalphState) -> dict[str, Any]:
    """Attempt to reproduce a bug by running tests and capturing error context."""
    from agents.tools.shell import _extract_traceback, _run

    root_path = None
    try:
        from agents.core.paths import repo_root as _repo_root

        root_path = _repo_root()
    except Exception:
        pass

    steps = ["pytest --tb=long -x"]
    returncode, stdout, stderr = _run(
        ["python", "-m", "pytest", "--tb=long", "-x", "-q"],
        cwd=root_path,
    )
    combined = stdout + stderr
    traceback_text = _extract_traceback(combined)
    reproduced = returncode != 0

    error_context = None
    if reproduced:
        relevant_logs = [
            line.strip()
            for line in combined.splitlines()
            if any(kw in line.lower() for kw in ("error", "failed", "exception", "assert"))
        ][:20]
        error_context = ErrorContext(
            command="pytest --tb=long -x",
            returncode=returncode,
            stdout=stdout[:4000],
            stderr=stderr[:4000],
            traceback=traceback_text,
            relevant_logs=relevant_logs,
        )

    result = ReproductionResult(
        reproduced=reproduced,
        steps_attempted=steps,
        error_context=error_context,
        summary=f"Bug {'reproduced' if reproduced else 'not reproduced'} via pytest",
    )

    logfire.info(
        "reproduce_complete",
        reproduced=reproduced,
        traceback_length=len(traceback_text),
    )

    return {"reproduction_evidence": result, "total_tool_calls": state["total_tool_calls"] + 1}


async def implement_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "implement_node")
    if not guard.allowed:
        return {
            "status": "escalated" if guard.action == "escalate" else "failed",
            "error_log": state["error_log"] + [guard.reason],
        }

    iteration = state["iteration_count"] + 1
    context = build_context(state["task"])
    impl, usage = await run_implementer(
        task=state["task"],
        plan=state["plan"],
        context=context,
        previous_validation=state["validation"],
        iteration=iteration,
        reproduction_evidence=state.get("reproduction_evidence"),
    )

    from agents.core.paths import repo_root as _repo_root

    root = _repo_root()

    for change in impl.files_changed:
        target = root / change.path
        if change.operation == "delete":
            target.unlink(missing_ok=True)
        elif change.content is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")

    return {
        "files_changed": impl.files_changed,
        "iteration_count": iteration,
        **_accumulate_usage(state, usage, "implement_node"),
        "total_tool_calls": state["total_tool_calls"] + 1,
        "status": "validating",
    }


async def validate_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    validation = await run_validator(iteration=state["iteration_count"])
    return {
        "validation": validation,
        "total_tool_calls": state["total_tool_calls"] + 2,  # run_tests + run_lint
        "status": "validating",
    }


def route_after_validate(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    validation = state["validation"]
    if validation is None:
        return "human_checkpoint"
    route_map = {
        "proceed": "perf_validate_node",
        "retry": "implement_node",
        "escalate": "human_checkpoint",
    }
    return route_map[validation.next_action]


async def perf_validate_node(state: RalphState) -> dict[str, Any]:
    """Run benchmarks and compare against baseline. Informational only in v1."""
    plan = state["plan"]
    if plan and plan.risk_level == "low":
        logfire.info("perf_validate_skipped", reason="low risk change")
        return {}

    try:
        from agents.tools.benchmark import compare_benchmarks, run_benchmark

        current = await run_benchmark.fn()
        baseline = state["perf_baseline"]
        if baseline is None:
            comparison = PerfComparisonResult(current=current, verdict="no_baseline")
        else:
            comparison = await compare_benchmarks.fn(baseline=baseline, current=current)
        if comparison.verdict == "regressed":
            logfire.warning(
                "perf_regression_detected",
                regressions=comparison.regressions,
            )
        return {"perf_result": comparison, "total_tool_calls": state["total_tool_calls"] + 1}
    except Exception as e:
        logfire.warning("perf_validate_failed", error=str(e))
        return {}


async def ui_validate_node(state: RalphState) -> dict[str, Any]:
    """Capture browser screenshots when the plan flags UI changes.

    Requires APP_URL env var (set by worktree_up.sh). Skips gracefully if not set
    or if plan.requires_browser_validation is False.
    """
    plan = state["plan"]
    if not plan or not plan.requires_browser_validation:
        return {}

    app_url = os.environ.get("APP_URL", "")
    if not app_url:
        logfire.warning("ui_validate_skipped", reason="APP_URL env var not set")
        return {}

    try:
        from agents.tools.harness import run_app_and_probe

        startup = await run_app_and_probe.fn()
        if not startup.started:
            logfire.warning("ui_validate_app_not_started", error=startup.error)
    except Exception as e:
        logfire.warning("ui_validate_harness_probe_failed", error=str(e))

    try:
        from agents.tools.browser import snapshot_dom, take_screenshot

        screenshot = await take_screenshot.fn(app_url)
        dom = await snapshot_dom.fn(app_url)
        logfire.info(
            "ui_validate_complete",
            url=app_url,
            title=dom.title,
            screenshot_bytes=len(screenshot.image_base64),
        )
        return {
            "ui_screenshots": state["ui_screenshots"] + [screenshot.image_base64],
            "total_tool_calls": state["total_tool_calls"] + 3,
        }
    except Exception as e:
        logfire.warning("ui_validate_failed", error=str(e), url=app_url)
        return {"total_tool_calls": state["total_tool_calls"] + 1}


async def open_pr_node(state: RalphState) -> dict[str, Any]:
    changed_paths = [f.path for f in state["files_changed"]]
    commit_result = await commit.fn(
        message=f"feat: {state['task'][:72]}",
        files=changed_paths,
    )
    if not commit_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Commit failed: {commit_result.error}"],
        }

    screenshot_note = ""
    if state["ui_screenshots"]:
        screenshot_note = f"\n\n## UI Validation\n{len(state['ui_screenshots'])} screenshot(s) captured before this PR."

    pr_result = await open_pr.fn(
        title=state["task"][:72],
        body=(
            f"## Task\n{state['task']}\n\n"
            f"## Changes\n"
            + "\n".join(f"- `{f.path}` ({f.operation})" for f in state["files_changed"])
            + screenshot_note
        ),
    )
    if not pr_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"PR creation failed: {pr_result.error}"],
        }

    return {
        "pr_url": pr_result.url,
        "pr_number": pr_result.number,
        "total_tool_calls": state["total_tool_calls"] + 2,  # commit + open_pr
        "status": "reviewing",
    }


async def review_loop_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "review_loop_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    review, usage = await run_reviewer(state["pr_number"], state["task"])
    return {
        "review": review,
        "review_iteration_count": state["review_iteration_count"] + 1,
        **_accumulate_usage(state, usage, "review_loop_node"),
        "total_tool_calls": state["total_tool_calls"] + 1,  # get_pr_diff in reviewer
    }


def route_after_review(state: RalphState) -> str:
    if state["status"] == "escalated":
        return "human_checkpoint"
    review = state["review"]
    if review is None or not review.approved:
        if state["review_iteration_count"] >= 3:
            return "human_checkpoint"
        return "implement_node"
    return "merge_node"


async def merge_node(state: RalphState) -> dict[str, Any]:
    result = await merge_pr.fn(pr_number=state["pr_number"])
    if not result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Merge failed: {result.error}"],
        }
    return {"status": "done", "total_tool_calls": state["total_tool_calls"] + 1}


async def human_checkpoint(state: RalphState) -> dict[str, Any]:
    logfire.warning(
        "human_escalation_required",
        task=state["task"],
        iteration_count=state["iteration_count"],
        error_log=state["error_log"],
        status=state["status"],
    )
    return {"status": "escalated", "total_tool_calls": state["total_tool_calls"]}


def build_ralph_graph() -> StateGraph:
    graph = StateGraph(RalphState)

    graph.add_node("plan_node", plan_node)
    graph.add_node("reproduce_node", reproduce_node)
    graph.add_node("implement_node", implement_node)
    graph.add_node("validate_node", validate_node)
    graph.add_node("perf_validate_node", perf_validate_node)
    graph.add_node("ui_validate_node", ui_validate_node)
    graph.add_node("open_pr_node", open_pr_node)
    graph.add_node("review_loop_node", review_loop_node)
    graph.add_node("merge_node", merge_node)
    graph.add_node("human_checkpoint", human_checkpoint)

    graph.set_entry_point("plan_node")
    graph.add_conditional_edges("plan_node", route_after_plan)
    graph.add_edge("reproduce_node", "implement_node")
    graph.add_edge("implement_node", "validate_node")
    graph.add_conditional_edges("validate_node", route_after_validate)
    graph.add_edge("perf_validate_node", "ui_validate_node")
    graph.add_edge("ui_validate_node", "open_pr_node")
    graph.add_edge("open_pr_node", "review_loop_node")
    graph.add_conditional_edges("review_loop_node", route_after_review)
    graph.add_edge("merge_node", END)
    graph.add_edge("human_checkpoint", END)

    return graph


async def run_ralph_loop(task: str) -> RalphState:
    """Entry point: run the full Ralph Loop for a task. Returns final state."""
    start_time = time.monotonic()

    with logfire.span("ralph_loop", task=task[:100]):
        graph = build_ralph_graph()
        app = graph.compile()

        state = initial_state(task)
        final_state = await app.ainvoke(state)

        duration = time.monotonic() - start_time
        total_cost = final_state["estimated_cost_usd"]

        logfire.info(
            "ralph_loop_complete",
            task=task[:100],
            status=final_state["status"],
            iterations=final_state["iteration_count"],
            duration_seconds=duration,
            cost_usd=total_cost,
        )

        node_usage = final_state["node_token_usage"]
        per_node_costs = {}
        for node_name, usage_data in node_usage.items():
            node_cost = TokenUsage(
                tokens_in=usage_data["tokens_in"],
                tokens_out=usage_data["tokens_out"],
            ).cost_usd()
            per_node_costs[node_name] = CostSummary(
                tokens_in=usage_data["tokens_in"],
                tokens_out=usage_data["tokens_out"],
                cost_usd=node_cost,
                model="gemini-3.0-flash-preview",
                task=task[:200],
                workflow="ralph_loop",
                duration_seconds=duration,
                iterations=final_state["iteration_count"],
                tool_calls=0,
            )

        highest_cost_node = (
            max(per_node_costs, key=lambda n: per_node_costs[n].cost_usd)
            if per_node_costs
            else "none"
        )

        metrics = RunMetrics(
            cost=CostSummary(
                tokens_in=final_state["total_tokens_in"],
                tokens_out=final_state["total_tokens_out"],
                cost_usd=total_cost,
                model="gemini-3.0-flash-preview",
                task=task[:200],
                workflow="ralph_loop",
                duration_seconds=duration,
                iterations=final_state["iteration_count"],
                tool_calls=final_state["total_tool_calls"],
            ),
            per_node_costs=per_node_costs,
            highest_cost_node=highest_cost_node,
        )
        logfire.info("run_metrics", **metrics.model_dump())

    return final_state
