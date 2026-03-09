"""Extended Golden Principles linter — GP-011 through GP-014.

Split from golden_lint.py to comply with GP-002 (max 500 lines).
"""

import ast
from pathlib import Path

from lint.rules import RULES_BY_ID


def _all_python_files(root: Path, exclude_scripts: bool = False) -> list[Path]:
    excluded = {".venv", "venv", "__pycache__", ".git", "dist", "build"}
    files = []
    for f in root.rglob("*.py"):
        parts = set(f.parts)
        if parts.intersection(excluded):
            continue
        if exclude_scripts and "scripts" in parts:
            continue
        files.append(f)
    return files


def check_gp011_cross_module_private_imports(root: Path) -> list[str]:
    """GP-011: Do not import _-prefixed names from other modules.

    Catches `from some.module import _private_thing` patterns.
    Excludes test files (test helpers may legitimately import internals for testing)
    and __init__.py re-exports.
    """
    violations = []
    for py_file in _all_python_files(root):
        rel = py_file.relative_to(root)
        if "tests" in rel.parts or rel.name == "__init__.py":
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if not node.module.startswith("agents."):
                continue
            file_module = str(rel).replace("/", ".").replace("\\", ".").removesuffix(".py")
            file_pkg = ".".join(file_module.split(".")[:-1])
            import_pkg = ".".join(node.module.split(".")[:-1])

            for alias in node.names:
                if alias.name.startswith("_") and not alias.name.startswith("__"):
                    if file_pkg == import_pkg:
                        continue
                    rule = RULES_BY_ID.get("GP-011")
                    remediation = (
                        rule.agent_remediation if rule else "Make the imported name public."
                    )
                    violations.append(
                        f"GP-011: {rel}:{node.lineno} imports private name "
                        f"'{alias.name}' from {node.module}.\n"
                        f"REMEDIATION: {remediation}"
                    )
    return violations


def check_gp012_file_encoding(root: Path) -> list[str]:
    """GP-012: All file I/O must specify encoding='utf-8' explicitly.

    Catches .read_text(), .write_text(), and open() without encoding= keyword.
    Prevents platform-dependent encoding bugs on Windows (cp1252 default).
    """
    violations = []
    for py_file in _all_python_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        rel = str(py_file.relative_to(root))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if isinstance(node.func, ast.Attribute) and node.func.attr in (
                "read_text",
                "write_text",
            ):
                has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
                if not has_encoding:
                    rule = RULES_BY_ID.get("GP-012")
                    remediation = rule.agent_remediation if rule else "Add encoding='utf-8'."
                    violations.append(
                        f"GP-012: {rel}:{node.lineno} "
                        f".{node.func.attr}() without explicit encoding.\n"
                        f"REMEDIATION: {remediation}"
                    )

            if isinstance(node.func, ast.Name) and node.func.id == "open":
                has_encoding = any(kw.arg == "encoding" for kw in node.keywords)
                has_positional_encoding = len(node.args) >= 4
                if not has_encoding and not has_positional_encoding:
                    is_binary = False
                    if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                        mode = str(node.args[1].value)
                        is_binary = "b" in mode
                    for kw in node.keywords:
                        if (
                            kw.arg == "mode"
                            and isinstance(kw.value, ast.Constant)
                            and "b" in str(kw.value.value)
                        ):
                            is_binary = True
                    if not is_binary:
                        rule = RULES_BY_ID.get("GP-012")
                        remediation = rule.agent_remediation if rule else "Add encoding='utf-8'."
                        violations.append(
                            f"GP-012: {rel}:{node.lineno} "
                            f"open() without explicit encoding.\n"
                            f"REMEDIATION: {remediation}"
                        )
    return violations


def check_gp013_silent_exception(root: Path) -> list[str]:
    """GP-013: No bare except that silently swallows errors.

    Catches `except Exception: return {}` and `except Exception: pass` patterns.
    Logging alone is not enough — the error must be propagated via error_log,
    re-raised, or returned in a structured result.
    """
    violations = []
    for py_file in _all_python_files(root):
        rel = py_file.relative_to(root)
        if set(rel.parts).intersection({"tests", "scripts", "lint"}):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if not (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                continue

            body = node.body
            has_return_empty = False
            has_pass = False
            has_error_propagation = False

            for stmt in body:
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    keys = {
                        k.value
                        for k in stmt.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
                    if not keys or not keys.intersection({"error_log", "status", "error"}):
                        has_return_empty = True
                if isinstance(stmt, ast.Pass):
                    has_pass = True
                if isinstance(stmt, ast.Raise):
                    has_error_propagation = True
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Dict):
                    keys = {
                        k.value
                        for k in stmt.value.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)
                    }
                    if "error_log" in keys or "error" in keys:
                        has_error_propagation = True

            if (has_return_empty or has_pass) and not has_error_propagation:
                rule = RULES_BY_ID.get("GP-013")
                remediation = (
                    rule.agent_remediation
                    if rule
                    else "Propagate the error via error_log or re-raise."
                )
                violations.append(
                    f"GP-013: {rel}:{node.lineno} "
                    f"except Exception swallows error silently.\n"
                    f"REMEDIATION: {remediation}"
                )
    return violations


def check_gp014_hardcoded_guard_limits(root: Path) -> list[str]:
    """GP-014: Guard limits must reference constants from guards.py, not magic numbers.

    Catches patterns like `state["review_iteration_count"] >= 3` outside guards.py.
    The canonical constants are in agents/core/guards.py.
    """
    violations = []
    from agents.core.guards import (
        MAX_IMPLEMENT_ITERATIONS,
        MAX_REVIEW_ITERATIONS,
        MAX_TOOL_CALLS_PER_NODE,
        MAX_TOTAL_TOOL_CALLS,
    )

    guard_values = {
        MAX_IMPLEMENT_ITERATIONS: "MAX_IMPLEMENT_ITERATIONS",
        MAX_REVIEW_ITERATIONS: "MAX_REVIEW_ITERATIONS",
        MAX_TOOL_CALLS_PER_NODE: "MAX_TOOL_CALLS_PER_NODE",
        MAX_TOTAL_TOOL_CALLS: "MAX_TOTAL_TOOL_CALLS",
    }

    guard_fields = {
        "iteration_count",
        "review_iteration_count",
        "total_tool_calls",
    }

    workflows_dir = root / "agents" / "workflows"
    if not workflows_dir.exists():
        return []

    for py_file in workflows_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        rel = str(py_file.relative_to(root))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.GtE, ast.Gt)) for op in node.ops):
                continue

            left = node.left
            is_guard_field = False
            if (
                isinstance(left, ast.Subscript)
                and isinstance(left.slice, ast.Constant)
                and left.slice.value in guard_fields
            ):
                is_guard_field = True

            if not is_guard_field:
                continue

            for comparator in node.comparators:
                if (
                    isinstance(comparator, ast.Constant)
                    and isinstance(comparator.value, (int, float))
                    and comparator.value in guard_values
                ):
                    const_name = guard_values[comparator.value]
                    rule = RULES_BY_ID.get("GP-014")
                    remediation = (
                        rule.agent_remediation
                        if rule
                        else f"Use {const_name} from agents.core.guards."
                    )
                    violations.append(
                        f"GP-014: {rel}:{node.lineno} "
                        f"hardcoded limit {comparator.value} should use "
                        f"{const_name} from agents.core.guards.\n"
                        f"REMEDIATION: {remediation}"
                    )
    return violations
