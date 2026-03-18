"""Tests for the mutation sampler — AST mutation transforms and scoring."""

import ast

from agents.tools.mutation_sampler import _apply_mutation, _find_mutable_lines


def test_find_comparison_candidates() -> None:
    source = "if x == 1:\n    return True"
    tree = ast.parse(source)
    candidates = _find_mutable_lines(tree)
    kinds = [k for _, k in candidates]
    assert "comparison" in kinds


def test_find_boolean_candidates() -> None:
    source = "x = True\ny = False"
    tree = ast.parse(source)
    candidates = _find_mutable_lines(tree)
    kinds = [k for _, k in candidates]
    assert kinds.count("boolean") >= 2


def test_find_return_candidates() -> None:
    source = "def f():\n    return 42"
    tree = ast.parse(source)
    candidates = _find_mutable_lines(tree)
    kinds = [k for _, k in candidates]
    assert "return" in kinds


def test_comparison_mutation_flips_eq() -> None:
    source = "if x == 1:\n    pass"
    mutated, desc = _apply_mutation(source, 1, "comparison")
    assert mutated is not None
    assert "!=" in mutated
    assert "comparison" in desc


def test_boolean_mutation_flips_true() -> None:
    source = "x = True"
    mutated, _desc = _apply_mutation(source, 1, "boolean")
    assert mutated is not None
    assert "False" in mutated


def test_return_mutation_returns_none() -> None:
    source = "def f():\n    return 42"
    mutated, _desc = _apply_mutation(source, 2, "return")
    assert mutated is not None
    assert "None" in mutated


def test_mutation_on_wrong_line_returns_none() -> None:
    source = "x = 1\ny = 2"
    mutated, _ = _apply_mutation(source, 1, "comparison")
    assert mutated is None


def test_mutation_result_model() -> None:
    from agents.models.mutation import MutantResult, MutationSamplingResult

    result = MutationSamplingResult(
        total_mutants=10,
        killed=7,
        survived=3,
        kill_rate=0.7,
        passed=True,
        survivors=[
            MutantResult(file="foo.py", line=5, mutation="== to !=", survived=True),
        ],
    )
    assert result.passed
    assert len(result.survivors) == 1
    assert result.kill_rate == 0.7
