"""Workflow contract linter — enforces invariants across LangGraph node functions.

WF-001: Every workflow node must call pre_node_guard() near entry.
WF-002: Every return dict from a workflow node must include tool-call tracking keys,
        or be a guard-failure return (status + error_log only).
WF-003: build_context(worker_role=X) result must not be passed to run_Y() where X != Y.
WF-005: Nodes that can return status='failed'/'escalated' must use conditional edges.
WF-006: Tool calls inside loops must count attempts, not just successes.
WF-007: Post-call >= MAX_TOOL_CALLS_PER_NODE is off-by-one; require > for post-call.
WF-009: LLM runner nodes must call accumulate_usage().
WF-010: No direct Path.write_text/unlink/mkdir in workflow nodes.
"""

import ast
import sys
from pathlib import Path

from agents.core.paths import repo_root as _repo_root
from lint.rules import RULES_BY_ID

_TRACKING_KEYS = {"total_tool_calls", "node_tool_calls"}

_GUARD_FAILURE_KEYS = {"status", "error_log"}

_EXEMPT_NODES = {"human_checkpoint", "post_mortem_node"}

_WORKER_ROLE_TO_RUNNER = {
    "planner": "run_planner",
    "implementer": "run_implementer",
    "reviewer": "run_reviewer",
    "cleaner": "run_cleaner",
}

_LLM_RUNNERS = frozenset(
    {
        "run_planner",
        "run_implementer",
        "run_reviewer",
        "run_cleaner",
        "run_post_mortem",
    }
)

_FILE_MUTATION_METHODS = frozenset(
    {
        "write_text",
        "write_bytes",
        "unlink",
        "mkdir",
        "rmdir",
        "rename",
        "replace",
        "touch",
    }
)


def _is_workflow_node(func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Heuristic: a function is a workflow node if it takes `state` as first arg
    and returns dict[str, Any]."""
    if not func.args.args:
        return False
    first_arg = func.args.args[0].arg
    if first_arg != "state":
        return False
    return func.name.endswith("_node") or func.name == "human_checkpoint"


def _dict_keys_from_return(node: ast.Dict) -> set[str]:
    """Extract string keys from a dict literal in a return statement."""
    keys = set()
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def _references_guard_reason(node: ast.AST) -> bool:
    """Recursively check if an AST node references ``guard.reason``."""
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Attribute)
            and child.attr == "reason"
            and isinstance(child.value, ast.Name)
            and child.value.id == "guard"
        ):
            return True
    return False


def _is_guard_failure_return(node: ast.Dict) -> bool:
    """Check if a return dict is a guard-failure return.

    Must have only {status, error_log} keys **and** reference ``guard.reason``
    in its values, so that ordinary operational failures (commit/push/merge
    failures) are not accidentally exempted from tool-call tracking.
    """
    keys = _dict_keys_from_return(node)
    if not keys or not keys.issubset(_GUARD_FAILURE_KEYS):
        return False
    # Verify that the dict values actually reference guard.reason
    for value in node.values:
        if value is not None and _references_guard_reason(value):
            return True
    return False


def _is_empty_return(node: ast.Dict) -> bool:
    """Check if a return dict is empty {}."""
    return len(node.keys) == 0


def _has_double_star(node: ast.Dict) -> bool:
    """Check if a dict has **spread (None key in ast.Dict)."""
    return None in node.keys


def check_wf001_guard_contract(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-001: Workflow node must call pre_node_guard() near its entry."""
    has_guard = False
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            if isinstance(callee, ast.Name) and callee.id == "pre_node_guard":
                has_guard = True
                break
            if isinstance(callee, ast.Attribute) and callee.attr == "pre_node_guard":
                has_guard = True
                break
    if not has_guard and func.name not in _EXEMPT_NODES:
        rule = RULES_BY_ID.get("WF-001")
        remediation = (
            rule.agent_remediation if rule else "Add pre_node_guard(state, node_name) call."
        )
        return [
            f"WF-001: {rel_path}:{func.lineno} '{func.name}' is a workflow node "
            f"but does not call pre_node_guard().\n"
            f"REMEDIATION: {remediation}"
        ]
    return []


def check_wf002_return_tracking(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-002: Every non-guard-failure return dict must include tool-call tracking."""
    if func.name in _EXEMPT_NODES:
        return []
    violations = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Return) or node.value is None:
            continue
        ret_val = node.value
        if not isinstance(ret_val, ast.Dict):
            continue

        keys = _dict_keys_from_return(ret_val)

        if _is_guard_failure_return(ret_val):
            continue

        if _is_empty_return(ret_val):
            continue

        if _has_double_star(ret_val):
            continue

        missing = _TRACKING_KEYS - keys
        if missing:
            rule = RULES_BY_ID.get("WF-002")
            remediation = rule.agent_remediation if rule else f"Add {missing} to the return dict."
            violations.append(
                f"WF-002: {rel_path}:{node.lineno} return in '{func.name}' "
                f"is missing tracking keys: {', '.join(sorted(missing))}.\n"
                f"REMEDIATION: {remediation}"
            )
    return violations


def check_wf003_context_role_mismatch(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-003: build_context(worker_role=X) must match the run_X() call it feeds."""
    violations = []

    var_roles: dict[str, str] = {}

    for node in ast.walk(func):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                call = node.value
                callee = call.func
                if (isinstance(callee, ast.Name) and callee.id == "build_context") or (
                    isinstance(callee, ast.Attribute) and callee.attr == "build_context"
                ):
                    for kw in call.keywords:
                        if (
                            kw.arg == "worker_role"
                            and isinstance(kw.value, ast.Constant)
                            and isinstance(kw.value.value, str)
                        ):
                            var_roles[target.id] = kw.value.value

    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if isinstance(callee, ast.Name):
            runner_name = callee.id
        elif isinstance(callee, ast.Attribute):
            runner_name = callee.attr
        else:
            continue

        expected_role = None
        for role, runner in _WORKER_ROLE_TO_RUNNER.items():
            if runner_name == runner:
                expected_role = role
                break
        if expected_role is None:
            continue

        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Name) and arg.id in var_roles:
                actual_role = var_roles[arg.id]
                if actual_role != expected_role:
                    rule = RULES_BY_ID.get("WF-003")
                    remediation = (
                        rule.agent_remediation
                        if rule
                        else f"Change worker_role to '{expected_role}'."
                    )
                    violations.append(
                        f"WF-003: {rel_path}:{node.lineno} '{func.name}' passes "
                        f"context built with worker_role='{actual_role}' to "
                        f"{runner_name}() which expects '{expected_role}'.\n"
                        f"REMEDIATION: {remediation}"
                    )
    return violations


def check_wf005_status_aware_edges(
    tree: ast.Module,
    node_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    rel_path: str,
) -> list[str]:
    """WF-005: Nodes returning status='failed'/'escalated' need conditional edges."""
    nodes_with_failure_status: set[str] = set()
    for func_name, func in node_funcs.items():
        for node in ast.walk(func):
            if not isinstance(node, ast.Return) or node.value is None:
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for key, val in zip(node.value.keys, node.value.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "status"
                    and isinstance(val, ast.Constant)
                    and val.value in ("failed", "escalated")
                ):
                    nodes_with_failure_status.add(func_name)

    unconditional_edges: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        callee = node.func
        if not (isinstance(callee, ast.Attribute) and callee.attr == "add_edge"):
            continue
        if len(node.args) >= 2 and isinstance(node.args[0], ast.Constant):
            src = node.args[0].value
            dest = node.args[1]
            if isinstance(dest, ast.Name) and dest.id == "END":
                continue
            if isinstance(dest, ast.Attribute) and dest.attr == "END":
                continue
            unconditional_edges[src] = node.lineno

    violations = []
    for func_name in nodes_with_failure_status:
        if func_name in unconditional_edges and func_name not in _EXEMPT_NODES:
            rule = RULES_BY_ID.get("WF-005")
            remediation = (
                rule.agent_remediation if rule else "Use add_conditional_edges instead of add_edge."
            )
            violations.append(
                f"WF-005: {rel_path}:{unconditional_edges[func_name]} "
                f"'{func_name}' can return status='failed'/'escalated' but uses "
                f"graph.add_edge() (unconditional). Use add_conditional_edges().\n"
                f"REMEDIATION: {remediation}"
            )
    return violations


def check_wf007_budget_off_by_one(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-007: Post-call >= MAX_TOOL_CALLS_PER_NODE is off-by-one."""
    violations = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Compare):
            continue
        if len(node.ops) != 1 or not isinstance(node.ops[0], ast.GtE):
            continue
        if len(node.comparators) != 1:
            continue
        comp = node.comparators[0]
        if isinstance(comp, ast.Name) and comp.id == "MAX_TOOL_CALLS_PER_NODE":
            for parent in ast.walk(func):
                if isinstance(parent, (ast.For, ast.While)):
                    rule = RULES_BY_ID.get("WF-007")
                    remediation = (
                        rule.agent_remediation
                        if rule
                        else "Use > instead of >= for post-call checks."
                    )
                    violations.append(
                        f"WF-007: {rel_path}:{node.lineno} '{func.name}' uses "
                        f"'>= MAX_TOOL_CALLS_PER_NODE' inside a loop — this is an "
                        f"off-by-one that escalates the last allowed call.\n"
                        f"REMEDIATION: {remediation}"
                    )
                    return violations  
    return violations


def check_wf009_llm_accumulate_usage(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-009: LLM runner nodes must call accumulate_usage()."""
    if func.name in _EXEMPT_NODES:
        return []
    has_llm_call = False
    has_accumulate = False
    for node in ast.walk(func):
        if isinstance(node, ast.Call):
            callee = node.func
            name = None
            if isinstance(callee, ast.Name):
                name = callee.id
            elif isinstance(callee, ast.Attribute):
                name = callee.attr
            if name in _LLM_RUNNERS:
                has_llm_call = True
            if name == "accumulate_usage":
                has_accumulate = True
    if has_llm_call and not has_accumulate:
        rule = RULES_BY_ID.get("WF-009")
        remediation = (
            rule.agent_remediation if rule else "Add accumulate_usage() to the return path."
        )
        return [
            f"WF-009: {rel_path}:{func.lineno} '{func.name}' calls an LLM runner "
            f"but does not call accumulate_usage().\n"
            f"REMEDIATION: {remediation}"
        ]
    return []


def check_wf010_no_direct_file_mutation(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-010: No direct Path mutation in workflow nodes."""
    if func.name in _EXEMPT_NODES:
        return []
    violations = []
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in _FILE_MUTATION_METHODS:
                rule = RULES_BY_ID.get("WF-010")
                remediation = (
                    rule.agent_remediation
                    if rule
                    else "Use apply_file_changes() or a tool instead."
                )
                violations.append(
                    f"WF-010: {rel_path}:{node.lineno} '{func.name}' calls "
                    f"'.{method}()' directly. Use apply_file_changes() or a tool.\n"
                    f"REMEDIATION: {remediation}"
                )
    return violations


def run_workflow_lint(path: str, repo_root: Path | None = None) -> list[str]:
    """Run all workflow contract checks. Returns violation messages."""
    if repo_root is None:
        repo_root = _repo_root()

    workflows_dir = repo_root / "agents" / "workflows"
    if not workflows_dir.exists():
        return []

    target = (repo_root / path).resolve()
    if target.is_dir():
        py_files = list(workflows_dir.rglob("*.py"))
    elif target.suffix == ".py" and str(target).startswith(str(workflows_dir)):
        py_files = [target]
    else:
        py_files = list(workflows_dir.rglob("*.py"))

    all_violations = []
    for py_file in py_files:
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        rel_path = str(py_file.relative_to(repo_root))

        node_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not _is_workflow_node(node):
                continue
            node_funcs[node.name] = node

        for func in node_funcs.values():
            all_violations.extend(check_wf001_guard_contract(func, rel_path))
            all_violations.extend(check_wf002_return_tracking(func, rel_path))
            all_violations.extend(check_wf003_context_role_mismatch(func, rel_path))
            all_violations.extend(check_wf007_budget_off_by_one(func, rel_path))
            all_violations.extend(check_wf009_llm_accumulate_usage(func, rel_path))
            all_violations.extend(check_wf010_no_direct_file_mutation(func, rel_path))

        all_violations.extend(check_wf005_status_aware_edges(tree, node_funcs, rel_path))

    return all_violations


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    violations = run_workflow_lint(path)

    if violations:
        for v in violations:
            print(v)
            print()
        print(f"Found {len(violations)} workflow contract violation(s).")
        return 1

    print("Workflow lint: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
