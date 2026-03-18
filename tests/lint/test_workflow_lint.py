"""Tests for workflow contract lint rules (WF-001 through WF-010)."""

import ast
import textwrap

from lint.workflow_lint import (
    check_wf001_guard_contract,
    check_wf002_return_tracking,
    check_wf003_context_role_mismatch,
    check_wf005_status_aware_edges,
    check_wf007_budget_off_by_one,
    check_wf009_llm_accumulate_usage,
    check_wf010_no_direct_file_mutation,
)
from lint.workflow_lint_ext import (
    check_wf004_guard_exemption,
    check_wf006_loop_tool_accounting,
)


def _parse_func(source: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    tree = ast.parse(textwrap.dedent(source))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise ValueError("No function found in source")


# --- WF-001: Guard contract ---


def test_wf001_passes_with_guard():
    func = _parse_func("""
    async def plan_node(state):
        guard = pre_node_guard(state, "plan_node")
        if not guard.allowed:
            return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}
        return {"total_tool_calls": 1, "node_tool_calls": {}}
    """)
    assert check_wf001_guard_contract(func, "test.py") == []


def test_wf001_fails_without_guard():
    func = _parse_func("""
    async def plan_node(state):
        return {"total_tool_calls": 1, "node_tool_calls": {}}
    """)
    violations = check_wf001_guard_contract(func, "test.py")
    assert len(violations) == 1
    assert "WF-001" in violations[0]
    assert "pre_node_guard" in violations[0]


# --- WF-002: Return tracking ---


def test_wf002_passes_with_tracking():
    func = _parse_func("""
    async def impl_node(state):
        return {"total_tool_calls": 5, "node_tool_calls": {"impl_node": 5}, "files": []}
    """)
    assert check_wf002_return_tracking(func, "test.py") == []


def test_wf002_fails_missing_tracking():
    func = _parse_func("""
    async def impl_node(state):
        return {"files": [], "status": "done"}
    """)
    violations = check_wf002_return_tracking(func, "test.py")
    assert len(violations) == 1
    assert "WF-002" in violations[0]
    assert "total_tool_calls" in violations[0]


def test_wf002_exempts_guard_failure_return():
    func = _parse_func("""
    async def impl_node(state):
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}
    """)
    assert check_wf002_return_tracking(func, "test.py") == []


def test_wf002_flags_non_guard_failure_missing_tracking():
    """Non-guard failures (e.g. commit/push failed) must include tracking keys."""
    func = _parse_func("""
    async def commit_push_node(state):
        return {"status": "failed", "error_log": state["error_log"] + ["Commit failed"]}
    """)
    violations = check_wf002_return_tracking(func, "test.py")
    assert len(violations) == 1
    assert "WF-002" in violations[0]


def test_wf002_exempts_empty_return():
    func = _parse_func("""
    async def skip_node(state):
        return {}
    """)
    assert check_wf002_return_tracking(func, "test.py") == []


def test_wf002_exempts_double_star_spread():
    func = _parse_func("""
    async def plan_node(state):
        return {"plan": plan, **accumulate_usage(state, usage, "plan_node", 1)}
    """)
    assert check_wf002_return_tracking(func, "test.py") == []


# --- WF-003: Context role mismatch ---


def test_wf003_passes_matching_roles():
    func = _parse_func("""
    async def plan_node(state):
        ctx = build_context(task, worker_role="planner")
        plan = await run_planner(task, ctx)
    """)
    assert check_wf003_context_role_mismatch(func, "test.py") == []


def test_wf003_fails_mismatched_roles():
    func = _parse_func("""
    async def impl_node(state):
        ctx = build_context(task, worker_role="implementer")
        plan = await run_planner(task, ctx)
    """)
    violations = check_wf003_context_role_mismatch(func, "test.py")
    assert len(violations) == 1
    assert "WF-003" in violations[0]
    assert "implementer" in violations[0]
    assert "planner" in violations[0]


def test_wf003_passes_separate_contexts():
    func = _parse_func("""
    async def impl_node(state):
        planner_ctx = build_context(task, worker_role="planner")
        impl_ctx = build_context(task, worker_role="implementer")
        plan = await run_planner(task, planner_ctx)
        impl = await run_implementer(task, plan, impl_ctx)
    """)
    assert check_wf003_context_role_mismatch(func, "test.py") == []


# --- WF-005: Status-aware edges ---


def _parse_module(source: str) -> ast.Module:
    return ast.parse(textwrap.dedent(source))


def _collect_node_funcs(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    from lint.workflow_lint import _is_workflow_node

    funcs = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and _is_workflow_node(node):
            funcs[node.name] = node
    return funcs


def test_wf005_passes_with_conditional_edges():
    source = """
async def scan_node(state):
    return {"status": "failed", "error_log": ["err"]}

graph.add_conditional_edges("scan_node", route_fn)
"""
    tree = _parse_module(source)
    funcs = _collect_node_funcs(tree)
    assert check_wf005_status_aware_edges(tree, funcs, "test.py") == []


def test_wf005_fails_with_unconditional_edge():
    source = """
async def scan_node(state):
    return {"status": "failed", "error_log": ["err"]}

graph.add_edge("scan_node", "next_node")
"""
    tree = _parse_module(source)
    funcs = _collect_node_funcs(tree)
    violations = check_wf005_status_aware_edges(tree, funcs, "test.py")
    assert len(violations) == 1
    assert "WF-005" in violations[0]
    assert "scan_node" in violations[0]


def test_wf005_passes_terminal_edge_to_end():
    """Edge to END is fine even if the node can fail — it's the terminal state."""
    source = """
async def reply_node(state):
    return {"status": "escalated", "error_log": ["hit limit"]}

graph.add_edge("reply_node", END)
"""
    tree = _parse_module(source)
    funcs = _collect_node_funcs(tree)
    assert check_wf005_status_aware_edges(tree, funcs, "test.py") == []


def test_wf005_passes_no_failure_status():
    source = """
async def safe_node(state):
    return {"total_tool_calls": 1, "node_tool_calls": {}}

graph.add_edge("safe_node", "next_node")
"""
    tree = _parse_module(source)
    funcs = _collect_node_funcs(tree)
    assert check_wf005_status_aware_edges(tree, funcs, "test.py") == []


# --- WF-007: Budget off-by-one ---


def test_wf007_flags_gte_in_loop():
    func = _parse_func("""
async def reply_node(state):
    for comment in comments:
        attempts += 1
        if existing + attempts >= MAX_TOOL_CALLS_PER_NODE:
            break
""")
    violations = check_wf007_budget_off_by_one(func, "test.py")
    assert len(violations) == 1
    assert "WF-007" in violations[0]
    assert "off-by-one" in violations[0]


def test_wf007_passes_gt_in_loop():
    func = _parse_func("""
async def reply_node(state):
    for comment in comments:
        attempts += 1
        if existing + attempts > MAX_TOOL_CALLS_PER_NODE:
            break
""")
    assert check_wf007_budget_off_by_one(func, "test.py") == []


def test_wf007_passes_no_loop():
    func = _parse_func("""
async def plan_node(state):
    if calls >= MAX_TOOL_CALLS_PER_NODE:
        return {}
""")
    assert check_wf007_budget_off_by_one(func, "test.py") == []


# --- WF-009: LLM accumulate_usage ---


def test_wf009_passes_with_accumulate():
    func = _parse_func("""
async def plan_node(state):
    plan, usage, tc = await run_planner(task, ctx)
    return {"plan": plan, **accumulate_usage(state, usage, "plan_node", tc)}
""")
    assert check_wf009_llm_accumulate_usage(func, "test.py") == []


def test_wf009_fails_without_accumulate():
    func = _parse_func("""
async def review_node(state):
    review, usage = await run_reviewer(pr, task)
    return {"review": review, "total_tool_calls": 1, "node_tool_calls": {}}
""")
    violations = check_wf009_llm_accumulate_usage(func, "test.py")
    assert len(violations) == 1
    assert "WF-009" in violations[0]
    assert "accumulate_usage" in violations[0]


def test_wf009_passes_no_llm_call():
    func = _parse_func("""
async def commit_node(state):
    result = commit(message="fix")
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    assert check_wf009_llm_accumulate_usage(func, "test.py") == []


# --- WF-010: No direct file mutation ---


def test_wf010_flags_write_text():
    func = _parse_func("""
async def update_node(state):
    path.write_text("content")
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    violations = check_wf010_no_direct_file_mutation(func, "test.py")
    assert len(violations) == 1
    assert "WF-010" in violations[0]
    assert "write_text" in violations[0]


def test_wf010_flags_unlink():
    func = _parse_func("""
async def cleanup_node(state):
    path.unlink()
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    violations = check_wf010_no_direct_file_mutation(func, "test.py")
    assert len(violations) == 1
    assert "unlink" in violations[0]


def test_wf010_passes_apply_file_changes():
    func = _parse_func("""
async def impl_node(state):
    apply_file_changes(impl.files_changed)
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    assert check_wf010_no_direct_file_mutation(func, "test.py") == []


# --- WF-004: Guard exemption requires listing ---


def test_wf004_flags_unguarded_non_exempt_node():
    func = _parse_func("""
async def rogue_node(state):
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    violations = check_wf004_guard_exemption(func, "test.py")
    assert len(violations) == 1
    assert "WF-004" in violations[0]
    assert "rogue_node" in violations[0]


def test_wf004_passes_guarded_node():
    func = _parse_func("""
async def plan_node(state):
    guard = pre_node_guard(state, "plan_node")
    if not guard.allowed:
        return {"status": "escalated", "error_log": state["error_log"] + [guard.reason]}
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    assert check_wf004_guard_exemption(func, "test.py") == []


def test_wf004_passes_exempt_node():
    func = _parse_func("""
def human_checkpoint(state):
    return {"status": "escalated"}
""")
    assert check_wf004_guard_exemption(func, "test.py") == []


# --- WF-006: Loop tool call accounting ---


def test_wf006_flags_loop_without_counter():
    func = _parse_func("""
async def reply_node(state):
    for comment in comments:
        result = reply_to_pr_comment(comment.id, "done")
""")
    violations = check_wf006_loop_tool_accounting(func, "test.py")
    assert len(violations) == 1
    assert "WF-006" in violations[0]


def test_wf006_passes_loop_with_attempts_counter():
    func = _parse_func("""
async def reply_node(state):
    for comment in comments:
        attempts += 1
        result = reply_to_pr_comment(comment.id, "done")
""")
    assert check_wf006_loop_tool_accounting(func, "test.py") == []


def test_wf006_passes_no_loop():
    func = _parse_func("""
async def plan_node(state):
    result = await run_planner(task, ctx)
    return {"total_tool_calls": 1, "node_tool_calls": {}}
""")
    assert check_wf006_loop_tool_accounting(func, "test.py") == []
