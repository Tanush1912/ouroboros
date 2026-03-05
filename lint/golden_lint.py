"""Golden Principles linter — GP-001 through GP-010.

Enforces the machine-checkable rules in docs/GOLDEN_PRINCIPLES.md.
"""

import ast
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from agents.core.paths import repo_root as _repo_root
from lint.rules import RULES_BY_ID

_GP006_ALLOWED_SUFFIXES = (
    "Output",
    "Result",
    "Schema",
    "Type",
    "Summary",
    "State",
    "Context",
    "Config",
    "Snapshot",
    "Capability",
    "Rule",
    "Change",
    "Comment",
    "Violation",
    "Action",
    "Snippet",
    "Reference",
    "Step",
    "Node",
    "Metrics",
    "Status",
    "Usage",
)


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


def check_gp001_duplicates(root: Path) -> list[str]:
    """GP-001: No duplicate utility functions across packages."""
    violations = []
    func_bodies: dict[str, list[str]] = {}

    for py_file in _all_python_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                body_source = ast.unparse(node)
                func_bodies.setdefault(body_source, []).append(
                    f"{py_file.relative_to(root)}:{node.name}"
                )

    for _body, locations in func_bodies.items():
        if len(locations) > 1:
            rule = RULES_BY_ID["GP-001"]
            violations.append(
                f"GP-001: Duplicate function detected in {len(locations)} locations:\n"
                + "\n".join(f"  - {loc}" for loc in locations)
                + f"\nREMEDIATION: {rule.agent_remediation}"
            )
    return violations


def check_gp002_file_size(root: Path) -> list[str]:
    """GP-002: No file exceeds 500 lines."""
    violations = []
    for py_file in _all_python_files(root):
        lines = py_file.read_text(encoding="utf-8").splitlines()
        if len(lines) > 500:
            rule = RULES_BY_ID["GP-002"]
            violations.append(
                f"GP-002: {py_file.relative_to(root)} has {len(lines)} lines (max 500).\n"
                f"REMEDIATION: {rule.agent_remediation}"
            )
    return violations


def check_gp003_hand_rolled(root: Path) -> list[str]:
    """GP-003: Detect hand-rolled reimplementations of standard patterns.

    Specifically catches while-loop + sleep retry patterns that should use tenacity.
    """
    violations = []
    for py_file in _all_python_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            has_while = any(isinstance(n, ast.While) for n in ast.walk(node))
            has_sleep = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "sleep"
                for n in ast.walk(node)
            )
            if has_while and has_sleep:
                rule = RULES_BY_ID["GP-003"]
                violations.append(
                    f"GP-003: {py_file.relative_to(root)}:{node.lineno} "
                    f"'{node.name}' implements a hand-rolled retry (while + sleep). "
                    f"Use tenacity.retry instead.\n"
                    f"REMEDIATION: {rule.agent_remediation}"
                )
    return violations


def check_gp004_unvalidated_external(root: Path) -> list[str]:
    """GP-004: External data (json.loads from subprocess/HTTP) must go through Pydantic.

    Flags functions that call json.loads() without a corresponding model_validate call.
    Excludes repo_index/ (reads its own generated data) and tests/.
    """
    violations = []
    excluded_dirs = {"repo_index", "tests", ".venv", "venv"}

    for py_file in _all_python_files(root):
        parts = set(py_file.relative_to(root).parts)
        if parts.intersection(excluded_dirs):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            has_json_loads = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "loads"
                and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "json"
                for n in ast.walk(node)
            )
            if not has_json_loads:
                continue

            has_validation = any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr in ("model_validate", "model_validate_json", "parse_obj")
                for n in ast.walk(node)
            )
            if not has_validation:
                rule = RULES_BY_ID["GP-004"]
                violations.append(
                    f"GP-004: {py_file.relative_to(root)}:{node.lineno} "
                    f"'{node.name}' calls json.loads() without Pydantic validation.\n"
                    f"REMEDIATION: {rule.agent_remediation}"
                )
    return violations


def check_gp005_no_print(root: Path) -> list[str]:
    """GP-005: No print() outside scripts/."""
    violations = []
    for py_file in _all_python_files(root, exclude_scripts=True):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                rule = RULES_BY_ID["GP-005"]
                violations.append(
                    f"GP-005: print() call in {py_file.relative_to(root)}:{node.lineno}\n"
                    f"REMEDIATION: {rule.agent_remediation}"
                )
    return violations


def check_gp006_model_naming(root: Path) -> list[str]:
    """GP-006: Pydantic BaseModel subclasses in agents/models/ must use approved suffixes."""
    violations = []
    models_dir = root / "agents" / "models"
    if not models_dir.exists():
        return []

    for py_file in models_dir.glob("*.py"):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            base_names = [
                b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else ""
                for b in node.bases
            ]
            if "BaseModel" not in base_names:
                continue
            if not any(node.name.endswith(s) for s in _GP006_ALLOWED_SUFFIXES):
                rule = RULES_BY_ID["GP-006"]
                violations.append(
                    f"GP-006: {py_file.relative_to(root)}:{node.lineno} "
                    f"'{node.name}' does not follow naming convention "
                    f"(*Output/*Result/*Schema/etc).\n"
                    f"REMEDIATION: {rule.agent_remediation}"
                )
    return violations


def check_gp007_dead_imports(root: Path) -> list[str]:
    """GP-007: No unused imports — delegates to ruff F401."""
    result = subprocess.run(
        ["python", "-m", "ruff", "check", "--select", "F401", "--output-format", "text", "."],
        capture_output=True,
        text=True,
        cwd=root,
    )
    if result.returncode == 0:
        return []

    rule = RULES_BY_ID["GP-007"]
    violations = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line and "F401" in line:
            violations.append(f"GP-007: {line}\nREMEDIATION: {rule.agent_remediation}")
    return violations


def check_gp009_active_plans(root: Path) -> list[str]:
    """GP-009: All active plans updated within 7 days."""
    violations = []
    plans_dir = root / "docs" / "exec-plans" / "active"
    if not plans_dir.exists():
        return []

    threshold = datetime.now(tz=UTC) - timedelta(days=7)

    for plan_file in plans_dir.glob("*.md"):
        content = plan_file.read_text(encoding="utf-8")
        match = re.search(r"\*\*Last Updated:\*\*\s*(\d{4}-\d{2}-\d{2})", content)
        if not match:
            violations.append(
                f"GP-009: {plan_file.name} has no 'Last Updated' field.\n"
                f"REMEDIATION: Add '**Last Updated:** YYYY-MM-DD' to the plan."
            )
            continue

        date_str = match.group(1)
        try:
            plan_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
        except ValueError:
            continue

        if plan_date < threshold:
            rule = RULES_BY_ID["GP-009"]
            violations.append(
                f"GP-009: {plan_file.name} last updated {date_str} (>7 days ago).\n"
                f"REMEDIATION: {rule.agent_remediation}"
            )

    return violations


def check_gp010_quality_score(root: Path) -> list[str]:
    """GP-010: QUALITY_SCORE.md must be current (< 24h)."""
    score_path = root / "docs" / "QUALITY_SCORE.md"
    if not score_path.exists():
        return [
            "GP-010: docs/QUALITY_SCORE.md does not exist.\n"
            "REMEDIATION: Run python agents/workflows/entropy_gc.py to generate it."
        ]

    import os

    mtime = datetime.fromtimestamp(os.path.getmtime(score_path), tz=UTC)
    age = datetime.now(tz=UTC) - mtime
    if age > timedelta(hours=24):
        rule = RULES_BY_ID["GP-010"]
        return [
            f"GP-010: docs/QUALITY_SCORE.md is {int(age.total_seconds()) // 3600}h old (max 24h).\n"
            f"REMEDIATION: {rule.agent_remediation}"
        ]
    return []


def run_golden_lint(path: str, repo_root: Path | None = None) -> list[str]:
    """Run all Golden Principle checks. Returns violation messages."""
    if repo_root is None:
        repo_root = _repo_root()

    violations = []
    violations.extend(check_gp002_file_size(repo_root))
    violations.extend(check_gp003_hand_rolled(repo_root))
    violations.extend(check_gp004_unvalidated_external(repo_root))
    violations.extend(check_gp005_no_print(repo_root))
    violations.extend(check_gp006_model_naming(repo_root))
    violations.extend(check_gp007_dead_imports(repo_root))
    violations.extend(check_gp009_active_plans(repo_root))
    violations.extend(check_gp010_quality_score(repo_root))
    violations.extend(check_gp001_duplicates(repo_root))
    return violations


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    violations = run_golden_lint(path)

    if violations:
        for v in violations:
            print(v)
            print()
        print(f"Found {len(violations)} golden principle violation(s).")
        return 1

    print("Golden lint: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
