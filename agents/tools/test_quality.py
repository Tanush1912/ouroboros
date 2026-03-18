"""AST-based test quality analyzer — deterministic, zero LLM cost.

Catches degenerate AI-generated tests: vacuous assertions, empty bodies,
untested files, missing edge case coverage. Scoring starts at 100 and
deducts for each quality issue found.
"""

import ast
from pathlib import Path

from agents.core.paths import repo_root as _repo_root
from agents.models.implementer import FileChange
from agents.models.test_quality import TestQualityResult

_QUALITY_THRESHOLD = 60


def _find_test_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    """Extract all test_* functions from an AST."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def _count_asserts(func: ast.FunctionDef) -> int:
    """Count assert statements in a function."""
    return sum(1 for node in ast.walk(func) if isinstance(node, ast.Assert))


def _is_trivial_assert(node: ast.Assert) -> bool:
    """Check if an assert is trivially true (assert True, assert 1 == 1)."""
    test = node.test
    # assert True
    if isinstance(test, ast.Constant) and test.value is True:
        return True
    # assert 1 == 1, assert "x" == "x"
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        left = test.left
        right = test.comparators[0]
        if (
            isinstance(left, ast.Constant)
            and isinstance(right, ast.Constant)
            and left.value == right.value
        ):
            return True
    return False


def _is_sole_none_check(func: ast.FunctionDef) -> bool:
    """Check if a function's only assertion is 'assert x is not None'."""
    asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
    if len(asserts) != 1:
        return False
    test = asserts[0].test
    if (
        isinstance(test, ast.Compare)
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.IsNot)
        and isinstance(test.comparators[0], ast.Constant)
    ):
        return test.comparators[0].value is None
    return False


def _is_empty_body(func: ast.FunctionDef) -> bool:
    """Check if a function body is just 'pass' or a docstring + pass."""
    stmts = [
        s for s in func.body if not isinstance(s, ast.Expr) or not isinstance(s.value, ast.Constant)
    ]
    if not stmts:
        return True
    return len(stmts) == 1 and isinstance(stmts[0], ast.Pass)


def _has_edge_case_markers(func: ast.FunctionDef) -> bool:
    """Check if a test exercises error/edge paths."""
    for node in ast.walk(func):
        # pytest.raises usage
        if isinstance(node, ast.Attribute) and node.attr == "raises":
            return True
        # Negative assertions (assert not ..., assertFalse)
        if (
            isinstance(node, ast.Assert)
            and isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
        ):
            return True
        # Boundary values in assertions (0, -1, [], "", None as test inputs)
        if isinstance(node, ast.Call):
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value in (0, -1, "", None):
                    return True
                if isinstance(arg, ast.List) and len(arg.elts) == 0:
                    return True
        # pytest.parametrize
        if isinstance(node, ast.Attribute) and node.attr == "parametrize":
            return True
    return False


def _extract_imports(source: str) -> set[str]:
    """Extract all imported module names from source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _find_test_files(root: Path) -> list[Path]:
    """Find all test_*.py files under tests/."""
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return []
    return [
        f
        for f in tests_dir.rglob("test_*.py")
        if ".venv" not in f.parts and "__pycache__" not in f.parts
    ]


def analyze_test_quality(
    files_changed: list[FileChange],
    root: Path | None = None,
) -> TestQualityResult:
    """Analyze test quality for changed files. Returns deterministic quality score."""
    if root is None:
        root = _repo_root()

    # Anchor protection — flag any changes to tests/anchors/ as blocking
    anchor_violations = [fc.path for fc in files_changed if fc.path.startswith("tests/anchors/")]
    if anchor_violations:
        return TestQualityResult(
            score=0.0,
            passed=False,
            assertion_density=0.0,
            trivial_test_count=0,
            untested_files=[],
            banned_patterns=[],
            edge_case_coverage=0.0,
            details=[
                f"BLOCKING: Agent modified anchor file(s): {', '.join(anchor_violations)}. "
                "Anchor files are human-authored invariants that agents must never change."
            ],
        )

    score = 100.0
    details: list[str] = []
    banned_patterns: list[str] = []
    trivial_count = 0
    total_asserts = 0
    total_test_funcs = 0
    edge_case_tests = 0

    # Separate production files from test files
    prod_files = [
        fc.path
        for fc in files_changed
        if not fc.path.startswith("tests/") and fc.path.endswith(".py")
    ]
    test_changes = [
        fc for fc in files_changed if fc.path.startswith("tests/") and fc.path.endswith(".py")
    ]

    # Analyze test files written by the agent
    for fc in test_changes:
        test_path = root / fc.path
        if not test_path.exists():
            continue
        try:
            source = test_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            details.append(f"{fc.path}: SyntaxError in test file")
            score -= 20
            continue

        test_funcs = _find_test_functions(tree)
        total_test_funcs += len(test_funcs)

        for func in test_funcs:
            asserts = _count_asserts(func)
            total_asserts += asserts

            # Check for empty/pass body
            if _is_empty_body(func):
                trivial_count += 1
                banned_patterns.append(f"{fc.path}:{func.lineno} {func.name} has empty/pass body")

            # Check for trivial asserts
            for node in ast.walk(func):
                if isinstance(node, ast.Assert) and _is_trivial_assert(node):
                    trivial_count += 1
                    banned_patterns.append(
                        f"{fc.path}:{node.lineno} {func.name} has trivial assert"
                    )

            # Check sole None check
            if _is_sole_none_check(func):
                trivial_count += 1
                banned_patterns.append(
                    f"{fc.path}:{func.lineno} {func.name} only asserts 'is not None'"
                )

            # Edge case detection
            if _has_edge_case_markers(func):
                edge_case_tests += 1

    # Also analyze existing test files for coverage of changed production files
    existing_test_files = _find_test_files(root)

    # Check which production files are tested (imported by any test file)
    tested_modules: set[str] = set()
    all_test_sources = []
    for tf in existing_test_files:
        try:
            source = tf.read_text(encoding="utf-8")
            all_test_sources.append(source)
            tested_modules.update(_extract_imports(source))
        except Exception:
            continue

    # Also check test files from the current change
    for fc in test_changes:
        test_path = root / fc.path
        if test_path.exists():
            try:
                source = test_path.read_text(encoding="utf-8")
                tested_modules.update(_extract_imports(source))
            except Exception:
                continue

    untested_files = []
    for pf in prod_files:
        module_path = pf.removesuffix(".py").replace("/", ".")
        if not any(module_path in m or module_path.split(".")[-1] in m for m in tested_modules):
            untested_files.append(pf)

    # Compute metrics
    assertion_density = total_asserts / max(total_test_funcs, 1)
    edge_case_coverage = edge_case_tests / max(total_test_funcs, 1)

    # Scoring deductions
    if trivial_count > 0:
        deduction = min(trivial_count * 15, 45)
        score -= deduction
        details.append(f"Trivial tests: {trivial_count} found (-{deduction})")

    if untested_files:
        deduction = min(len(untested_files) * 10, 20)
        score -= deduction
        details.append(f"Untested files: {', '.join(untested_files)} (-{deduction})")

    if assertion_density < 1.5 and total_test_funcs > 0:
        score -= 25
        details.append(f"Low assertion density: {assertion_density:.1f} avg per test (-25)")

    if edge_case_coverage < 0.2 and total_test_funcs > 0:
        score -= 20
        details.append(f"Low edge case coverage: {edge_case_coverage:.0%} (-20)")

    # No test files at all for production changes
    if prod_files and not test_changes and total_test_funcs == 0:
        score -= 30
        details.append("No test files in change for production code (-30)")

    score = max(score, 0.0)

    return TestQualityResult(
        score=score,
        passed=score >= _QUALITY_THRESHOLD,
        assertion_density=assertion_density,
        trivial_test_count=trivial_count,
        untested_files=untested_files,
        banned_patterns=banned_patterns,
        edge_case_coverage=edge_case_coverage,
        details=details,
    )
