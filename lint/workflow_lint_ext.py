"""Extended workflow contract linter — WF-004 and WF-006.

Split from workflow_lint.py to comply with GP-002 (max 500 lines).
"""

import ast

from agents.core.guards import EXEMPT_NODES
from lint.rules import RULES_BY_ID


def check_wf004_guard_exemption(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-004: Nodes that skip pre_node_guard() must be listed in EXEMPT_NODES."""
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
    if not has_guard and func.name not in EXEMPT_NODES:
        rule = RULES_BY_ID.get("WF-004")
        remediation = (
            rule.agent_remediation if rule else "Add pre_node_guard() or add node to EXEMPT_NODES."
        )
        return [
            f"WF-004: {rel_path}:{func.lineno} '{func.name}' skips pre_node_guard() "
            f"but is not listed in EXEMPT_NODES.\n"
            f"REMEDIATION: {remediation}"
        ]
    return []


def check_wf006_loop_tool_accounting(
    func: ast.FunctionDef | ast.AsyncFunctionDef, rel_path: str
) -> list[str]:
    """WF-006: Tool calls inside for/while loops must track attempts, not just successes."""
    if func.name in EXEMPT_NODES:
        return []
    violations = []
    for node in ast.walk(func):
        if not isinstance(node, (ast.For, ast.While)):
            continue
        has_tool_call = False
        has_attempt_counter = False
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee = child.func
                name = None
                if isinstance(callee, ast.Attribute) and callee.attr == "fn":
                    has_tool_call = True
                elif isinstance(callee, ast.Name):
                    name = callee.id
                elif isinstance(callee, ast.Attribute):
                    name = callee.attr
                if name and name.startswith("run_"):
                    has_tool_call = True
            if (
                isinstance(child, ast.AugAssign)
                and isinstance(child.op, ast.Add)
                and isinstance(child.target, ast.Name)
                and child.target.id in ("attempts", "node_calls", "tool_calls", "call_count")
            ):
                has_attempt_counter = True
        if has_tool_call and not has_attempt_counter:
            rule = RULES_BY_ID.get("WF-006")
            remediation = rule.agent_remediation if rule else "Add an attempts counter in the loop."
            violations.append(
                f"WF-006: {rel_path}:{node.lineno} '{func.name}' has tool calls "
                f"inside a loop without an attempt counter.\n"
                f"REMEDIATION: {remediation}"
            )
    return violations
