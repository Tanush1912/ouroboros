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
from agents.core.workflow_helpers import (
    accumulate_usage,
    apply_file_changes,
    update_node_tool_calls,
)
from agents.models.benchmark import PerfComparisonResult
from agents.models.cost import CostSummary, RunMetrics, TokenUsage
from agents.models.reproducer import ErrorContext, ReproductionResult
from agents.tools.git import commit, merge_pr, open_pr
from agents.workers.implementer import run_implementer
from agents.workers.planner import run_planner
from agents.workers.reviewer import run_reviewer
from agents.workers.validator import run_validator
from agents.workflows.post_mortem import post_mortem_node
from agents.workflows.ralph_routing import (
    route_after_implement,
    route_after_merge,
    route_after_open_pr,
    route_after_perf_validate,
    route_after_plan,
    route_after_reproduce,
    route_after_review,
    route_after_ui_validate,
    route_after_validate,
)


async def plan_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "plan_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    context = build_context(state["task"], worker_role="planner")
    plan, usage, tool_calls = await run_planner(state["task"], context)
    node_calls = tool_calls + 1
    return {
        "plan": plan,
        "status": "implementing",
        **accumulate_usage(state, usage, "plan_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
    }


async def reproduce_node(state: RalphState) -> dict[str, Any]:
    """Attempt to reproduce a bug by running tests and capturing error context."""
    guard = pre_node_guard(state, "reproduce_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    from agents.tools.shell import extract_traceback, run_subprocess

    root_path = None
    try:
        from agents.core.paths import repo_root as _repo_root

        root_path = _repo_root()
    except Exception as e:
        logfire.warning("reproduce_node_repo_root_failed", error=str(e))

    steps = ["pytest --tb=long -x"]
    returncode, stdout, stderr = run_subprocess(
        ["python", "-m", "pytest", "--tb=long", "-x", "-q"],
        cwd=root_path,
    )
    combined = stdout + stderr
    traceback_text = extract_traceback(combined)
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

    return {
        "reproduction_evidence": result,
        "status": "implementing",
        "total_tool_calls": state["total_tool_calls"] + 1,
        "node_tool_calls": update_node_tool_calls(state, "reproduce_node", 1),
    }


async def implement_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "implement_node")
    if not guard.allowed:
        return {
            "status": "escalated" if guard.action == "escalate" else "failed",
            "error_log": state["error_log"] + [guard.reason],
        }

    iteration = state["iteration_count"] + 1
    context = build_context(state["task"], worker_role="implementer")
    impl, usage, tool_calls = await run_implementer(
        task=state["task"],
        plan=state["plan"],
        context=context,
        previous_validation=state["validation"],
        iteration=iteration,
        reproduction_evidence=state.get("reproduction_evidence"),
    )

    apply_file_changes(impl.files_changed)

    # Keep symbol index fresh for subsequent implement iterations
    from agents.tools.fs import reindex as _reindex_tool

    _reindex_tool([fc.path for fc in impl.files_changed])

    node_calls = tool_calls + 1
    return {
        "files_changed": impl.files_changed,
        "iteration_count": iteration,
        **accumulate_usage(state, usage, "implement_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "status": "validating",
    }


async def validate_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    validation = await run_validator(iteration=state["iteration_count"])
    node_calls = 2  # run_tests + run_lint
    return {
        "validation": validation,
        "status": "validating",
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "node_tool_calls": update_node_tool_calls(state, "validate_node", node_calls),
    }


async def perf_validate_node(state: RalphState) -> dict[str, Any]:
    """Run benchmarks and compare against baseline. Informational only in v1."""
    guard = pre_node_guard(state, "perf_validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    plan = state["plan"]
    if plan and plan.risk_level == "low":
        logfire.info("perf_validate_skipped", reason="low risk change")
        return {
            "total_tool_calls": state["total_tool_calls"],
            "node_tool_calls": update_node_tool_calls(state, "perf_validate_node", 0),
        }

    try:
        from agents.tools.benchmark import compare_benchmarks, run_benchmark

        current = run_benchmark()
        baseline = state["perf_baseline"]
        if baseline is None:
            comparison = PerfComparisonResult(current=current, verdict="no_baseline")
        else:
            comparison = compare_benchmarks(baseline=baseline, current=current)
        if comparison.verdict == "regressed":
            logfire.warning(
                "perf_regression_detected",
                regressions=comparison.regressions,
            )
        return {
            "perf_result": comparison,
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "perf_validate_node", 1),
        }
    except Exception as e:
        logfire.warning("perf_validate_failed", error=str(e))
        return {
            "error_log": state["error_log"] + [f"perf_validate_node failed: {e}"],
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "perf_validate_node", 1),
        }


async def ui_validate_node(state: RalphState) -> dict[str, Any]:
    """Capture browser screenshots when the plan flags UI changes.

    Requires APP_URL env var (set by worktree_up.sh). Skips gracefully if not set
    or if plan.requires_browser_validation is False.
    """
    guard = pre_node_guard(state, "ui_validate_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    plan = state["plan"]
    if not plan or not plan.requires_browser_validation:
        return {
            "total_tool_calls": state["total_tool_calls"],
            "node_tool_calls": update_node_tool_calls(state, "ui_validate_node", 0),
        }

    app_url = os.environ.get("APP_URL", "")
    if not app_url:
        logfire.warning("ui_validate_skipped", reason="APP_URL env var not set")
        return {
            "total_tool_calls": state["total_tool_calls"],
            "node_tool_calls": update_node_tool_calls(state, "ui_validate_node", 0),
        }

    try:
        from agents.tools.harness import run_app_and_probe

        startup = run_app_and_probe()
        if not startup.started:
            logfire.warning("ui_validate_app_not_started", error=startup.error)
    except Exception as e:
        logfire.warning("ui_validate_harness_probe_failed", error=str(e))

    try:
        from agents.tools.browser import snapshot_dom, take_screenshot

        screenshot = await take_screenshot(app_url)
        dom = await snapshot_dom(app_url)
        logfire.info(
            "ui_validate_complete",
            url=app_url,
            title=dom.title,
            screenshot_bytes=len(screenshot.image_base64),
        )
        return {
            "ui_screenshots": state["ui_screenshots"] + [screenshot.image_base64],
            "total_tool_calls": state["total_tool_calls"] + 3,
            "node_tool_calls": update_node_tool_calls(state, "ui_validate_node", 3),
        }
    except Exception as e:
        logfire.warning("ui_validate_failed", error=str(e), url=app_url)
        return {
            "error_log": state["error_log"] + [f"ui_validate_node failed: {e}"],
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "ui_validate_node", 1),
        }


async def open_pr_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "open_pr_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    changed_paths = [f.path for f in state["files_changed"]]
    commit_result = commit(
        message=f"feat: {state['task'][:72]}",
        files=changed_paths,
    )
    if not commit_result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Commit failed: {commit_result.error}"],
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "open_pr_node", 1),
        }

    screenshot_note = ""
    if state["ui_screenshots"]:
        screenshot_note = f"\n\n## UI Validation\n{len(state['ui_screenshots'])} screenshot(s) captured before this PR."

    pr_result = open_pr(
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
            "total_tool_calls": state["total_tool_calls"] + 2,
            "node_tool_calls": update_node_tool_calls(state, "open_pr_node", 2),
        }

    node_calls = 2  # commit + open_pr
    return {
        "pr_url": pr_result.url,
        "pr_number": pr_result.number,
        "total_tool_calls": state["total_tool_calls"] + node_calls,
        "node_tool_calls": update_node_tool_calls(state, "open_pr_node", node_calls),
        "status": "reviewing",
    }


async def review_loop_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "review_loop_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    review, usage = await run_reviewer(state["pr_number"], state["task"])
    node_calls = 1  # get_pr_diff in reviewer
    return {
        "review": review,
        "review_iteration_count": state["review_iteration_count"] + 1,
        **accumulate_usage(state, usage, "review_loop_node", node_calls),
        "total_tool_calls": state["total_tool_calls"] + node_calls,
    }


async def merge_node(state: RalphState) -> dict[str, Any]:
    guard = pre_node_guard(state, "merge_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}

    result = merge_pr(pr_number=state["pr_number"])
    if not result.success:
        return {
            "status": "failed",
            "error_log": state["error_log"] + [f"Merge failed: {result.error}"],
            "total_tool_calls": state["total_tool_calls"] + 1,
            "node_tool_calls": update_node_tool_calls(state, "merge_node", 1),
        }
    return {
        "status": "done",
        "total_tool_calls": state["total_tool_calls"] + 1,
        "node_tool_calls": update_node_tool_calls(state, "merge_node", 1),
    }


def human_checkpoint(state: RalphState) -> dict[str, Any]:
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
    graph.add_node("post_mortem_node", post_mortem_node)

    graph.set_entry_point("plan_node")
    graph.add_conditional_edges("plan_node", route_after_plan)
    graph.add_conditional_edges("reproduce_node", route_after_reproduce)
    graph.add_conditional_edges("implement_node", route_after_implement)
    graph.add_conditional_edges("validate_node", route_after_validate)
    graph.add_conditional_edges("perf_validate_node", route_after_perf_validate)
    graph.add_conditional_edges("ui_validate_node", route_after_ui_validate)
    graph.add_conditional_edges("open_pr_node", route_after_open_pr)
    graph.add_conditional_edges("review_loop_node", route_after_review)
    graph.add_conditional_edges("merge_node", route_after_merge)
    graph.add_edge("human_checkpoint", "post_mortem_node")
    graph.add_edge("post_mortem_node", END)

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
                model="gemini-2.5-flash",
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
                model="gemini-2.5-flash",
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
