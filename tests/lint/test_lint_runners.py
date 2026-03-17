"""Integration tests for lint runners — verify all checkers are called.

If a checker is accidentally removed from run_golden_lint() or
run_workflow_lint(), these tests catch it.
"""

import ast

from agents.core.paths import repo_root

_REPO = repo_root()


def _extract_calls_in_function(source: str, func_name: str, prefix: str) -> set[str]:
    """AST-extract all function calls matching a prefix inside a named function."""
    tree = ast.parse(source)
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = child.func
                    name = None
                    if isinstance(callee, ast.Name):
                        name = callee.id
                    elif isinstance(callee, ast.Attribute):
                        name = callee.attr
                    if name and name.startswith(prefix):
                        calls.add(name)
    return calls


def test_run_golden_lint_calls_all_gp_checkers() -> None:
    """Verify run_golden_lint() invokes every registered GP check + sub-runners."""
    source = (_REPO / "lint" / "golden_lint.py").read_text(encoding="utf-8")
    called = _extract_calls_in_function(source, "run_golden_lint", "check_gp")

    # Also check for sub-runners
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_golden_lint":
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    callee = child.func
                    name = None
                    if isinstance(callee, ast.Name):
                        name = callee.id
                    elif isinstance(callee, ast.Attribute):
                        name = callee.attr
                    if name and name.startswith("run_"):
                        called.add(name)

    expected = {
        # Core GP checks (golden_lint.py)
        "check_gp001_duplicates",
        "check_gp002_file_size",
        "check_gp003_hand_rolled",
        "check_gp004_unvalidated_external",
        "check_gp005_no_print",
        "check_gp006_model_naming",
        "check_gp007_dead_imports",
        "check_gp009_active_plans",
        "check_gp010_quality_score",
        # Extended GP checks (golden_lint_ext.py)
        "check_gp011_cross_module_private_imports",
        "check_gp012_file_encoding",
        "check_gp013_silent_exception",
        "check_gp014_hardcoded_guard_limits",
        # Sub-runners
        "run_doc_lint",
        "run_workflow_lint",
        "run_golden_lint",  # recursive reference in the function definition
    }
    # Remove self-reference
    called.discard("run_golden_lint")
    expected.discard("run_golden_lint")

    assert called == expected, (
        f"run_golden_lint() missing checkers: {expected - called}\n"
        f"Extra checkers: {called - expected}"
    )


def test_run_workflow_lint_calls_all_wf_checkers() -> None:
    """Verify run_workflow_lint() invokes every registered WF check."""
    source = (_REPO / "lint" / "workflow_lint.py").read_text(encoding="utf-8")
    called = _extract_calls_in_function(source, "run_workflow_lint", "check_wf")

    expected = {
        "check_wf001_guard_contract",
        "check_wf002_return_tracking",
        "check_wf003_context_role_mismatch",
        "check_wf004_guard_exemption",
        "check_wf005_status_aware_edges",
        "check_wf006_loop_tool_accounting",
        "check_wf007_budget_off_by_one",
        "check_wf009_llm_accumulate_usage",
        "check_wf010_no_direct_file_mutation",
    }

    assert called == expected, (
        f"run_workflow_lint() missing checkers: {expected - called}\n"
        f"Extra checkers: {called - expected}"
    )
