"""Tests for the AST-based test quality analyzer."""

from pathlib import Path

from agents.models.implementer import FileChange
from agents.tools.test_quality import analyze_test_quality
from tests.lint.helpers import write_py


def _fc(path: str, operation: str = "create") -> FileChange:
    return FileChange(path=path, operation=operation, content="", diff_summary="test")


# --- Banned pattern detection ---


def test_detects_assert_true(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        def test_always_passes():
            assert True
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")], root=tmp_path
    )
    assert result.trivial_test_count > 0
    assert any("trivial assert" in p for p in result.banned_patterns)


def test_detects_assert_literal_equality(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        def test_one_equals_one():
            assert 1 == 1
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")], root=tmp_path
    )
    assert result.trivial_test_count > 0


def test_detects_pass_body(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        def test_nothing():
            pass
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")], root=tmp_path
    )
    assert result.trivial_test_count > 0
    assert any("empty/pass" in p for p in result.banned_patterns)


def test_detects_sole_none_check(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        def test_exists():
            result = get_thing()
            assert result is not None
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")], root=tmp_path
    )
    assert result.trivial_test_count > 0
    assert any("is not None" in p for p in result.banned_patterns)


# --- Good tests pass ---


def test_good_test_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        import pytest
        from agents.core import foo

        def test_add_returns_sum():
            assert foo.add(1, 2) == 3
            assert foo.add(0, 0) == 0

        def test_add_negative():
            assert foo.add(-1, 1) == 0
            assert foo.add(-5, -3) == -8

        def test_add_raises_on_string():
            with pytest.raises(TypeError):
                foo.add("a", 1)
            assert foo.add(100, 200) == 300
    """,
    )
    write_py(tmp_path, "agents/core/foo.py", "def add(a, b): return a + b")
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")],
        root=tmp_path,
    )
    assert result.trivial_test_count == 0
    assert result.assertion_density >= 1.5
    assert result.score >= 60
    assert result.passed


# --- Assertion density ---


def test_low_assertion_density_penalized(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        def test_a():
            assert True is not False

        def test_b():
            x = 1 + 1

        def test_c():
            pass
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")],
        root=tmp_path,
    )
    assert result.assertion_density < 1.5


# --- Edge case detection ---


def test_edge_case_detection(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_foo.py",
        """
        import pytest

        def test_raises_on_zero():
            with pytest.raises(ZeroDivisionError):
                divide(1, 0)

        def test_normal():
            assert divide(4, 2) == 2
    """,
    )
    result = analyze_test_quality(
        [_fc("agents/core/foo.py"), _fc("tests/test_foo.py")],
        root=tmp_path,
    )
    assert result.edge_case_coverage >= 0.4


# --- Untested files ---


def test_untested_production_file_detected(tmp_path: Path) -> None:
    write_py(tmp_path, "tests/test_bar.py", "def test_bar(): assert 1 + 1 == 2")
    write_py(tmp_path, "agents/core/foo.py", "x = 1")
    result = analyze_test_quality([_fc("agents/core/foo.py")], root=tmp_path)
    assert "agents/core/foo.py" in result.untested_files


# --- Scoring ---


def test_perfect_score_for_comprehensive_tests(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "tests/test_calc.py",
        """
        import pytest
        from agents.core import calc

        def test_add_positive():
            assert calc.add(1, 2) == 3
            assert calc.add(100, 200) == 300

        def test_add_zero():
            assert calc.add(0, 0) == 0
            assert calc.add(5, 0) == 5

        def test_add_negative():
            assert calc.add(-1, -2) == -3
            assert calc.add(-1, 1) == 0

        def test_add_type_error():
            with pytest.raises(TypeError):
                calc.add("a", 1)
    """,
    )
    write_py(tmp_path, "agents/core/calc.py", "def add(a, b): return a + b")
    result = analyze_test_quality(
        [_fc("agents/core/calc.py"), _fc("tests/test_calc.py")],
        root=tmp_path,
    )
    assert result.score >= 80
    assert result.passed
    assert result.trivial_test_count == 0


def test_no_tests_scores_low(tmp_path: Path) -> None:
    result = analyze_test_quality([_fc("agents/core/foo.py")], root=tmp_path)
    assert result.score <= 60
    assert len(result.details) > 0


# --- determine_next_action integration ---


def test_determine_next_action_retries_on_quality_failure() -> None:
    from agents.models.test_quality import TestQualityResult
    from agents.models.validator import LintResult, TestResult, determine_next_action

    passing_tests = TestResult(passed=True, failures=[])
    passing_lint = LintResult(passed=True, violations=[])
    bad_quality = TestQualityResult(
        score=30,
        passed=False,
        assertion_density=0.5,
        trivial_test_count=3,
        edge_case_coverage=0.0,
        details=["Trivial tests: 3 found (-45)"],
    )
    action, summary = determine_next_action(
        passing_tests, passing_lint, passing_lint, 1, bad_quality
    )
    assert action == "retry"
    assert "quality" in summary.lower()


def test_determine_next_action_proceeds_on_quality_pass() -> None:
    from agents.models.test_quality import TestQualityResult
    from agents.models.validator import LintResult, TestResult, determine_next_action

    passing_tests = TestResult(passed=True, failures=[])
    passing_lint = LintResult(passed=True, violations=[])
    good_quality = TestQualityResult(
        score=85,
        passed=True,
        assertion_density=2.5,
        trivial_test_count=0,
        edge_case_coverage=0.5,
    )
    action, _ = determine_next_action(passing_tests, passing_lint, passing_lint, 1, good_quality)
    assert action == "proceed"
