"""Mutation sampler — applies random AST mutations and checks if tests catch them.

Zero LLM cost. Targets only changed production files. Restores originals
after each mutation run. Surviving mutants prove tests are insufficient.
"""

import ast
import copy
import random
import subprocess
from pathlib import Path

from agents.core.paths import repo_root as _repo_root
from agents.models.implementer import FileChange
from agents.models.mutation import MutantResult, MutationSamplingResult

_MUTATIONS_PER_FILE = 8
_MAX_TOTAL_MUTATIONS = 20
_KILL_RATE_THRESHOLD = 0.6


class _ComparisonMutator(ast.NodeTransformer):
    """Flip comparison operators: == → !=, < → >=, > → <=."""

    def __init__(self, target_line: int) -> None:
        self.target_line = target_line
        self.mutated = False

    def visit_Compare(self, node: ast.Compare) -> ast.Compare:
        if node.lineno == self.target_line and not self.mutated and node.ops:
            swaps = {
                ast.Eq: ast.NotEq,
                ast.NotEq: ast.Eq,
                ast.Lt: ast.GtE,
                ast.GtE: ast.Lt,
                ast.Gt: ast.LtE,
                ast.LtE: ast.Gt,
            }
            op = node.ops[0]
            new_op_cls = swaps.get(type(op))
            if new_op_cls:
                node.ops[0] = new_op_cls()
                self.mutated = True
        return self.generic_visit(node)


class _BooleanMutator(ast.NodeTransformer):
    """Flip boolean constants: True → False, False → True."""

    def __init__(self, target_line: int) -> None:
        self.target_line = target_line
        self.mutated = False

    def visit_Constant(self, node: ast.Constant) -> ast.Constant:
        if node.lineno == self.target_line and not self.mutated and isinstance(node.value, bool):
            node.value = not node.value
            self.mutated = True
        return node


class _ReturnNoneMutator(ast.NodeTransformer):
    """Replace return value with None."""

    def __init__(self, target_line: int) -> None:
        self.target_line = target_line
        self.mutated = False

    def visit_Return(self, node: ast.Return) -> ast.Return:
        if node.lineno == self.target_line and not self.mutated and node.value is not None:
            node.value = ast.Constant(value=None)
            self.mutated = True
        return node


def _find_mutable_lines(tree: ast.Module) -> list[tuple[int, str]]:
    """Find lines with mutable AST nodes. Returns (line, mutation_type) pairs."""
    candidates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and hasattr(node, "lineno"):
            candidates.append((node.lineno, "comparison"))
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, bool)
            and hasattr(node, "lineno")
        ):
            candidates.append((node.lineno, "boolean"))
        elif isinstance(node, ast.Return) and node.value is not None and hasattr(node, "lineno"):
            candidates.append((node.lineno, "return"))
    return candidates


def _apply_mutation(source: str, line: int, kind: str) -> tuple[str | None, str]:
    """Apply a single mutation. Returns (mutated_source, description) or (None, reason)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None, "parse error"

    mutator_map = {
        "comparison": _ComparisonMutator,
        "boolean": _BooleanMutator,
        "return": _ReturnNoneMutator,
    }
    mutator_cls = mutator_map.get(kind)
    if not mutator_cls:
        return None, f"unknown kind: {kind}"

    mutated_tree = copy.deepcopy(tree)
    mutator = mutator_cls(line)
    mutator.visit(mutated_tree)

    if not mutator.mutated:
        return None, "no mutation applied"

    try:
        ast.fix_missing_locations(mutated_tree)
        return ast.unparse(mutated_tree), f"{kind} mutation at line {line}"
    except Exception:
        return None, "unparse failed"


def _run_tests(root: Path) -> bool:
    """Run pytest quickly. Returns True if tests pass."""
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-x", "-q", "--tb=no"],
        capture_output=True,
        text=True,
        cwd=root,
        timeout=60,
    )
    return result.returncode == 0


def run_mutation_sampling(
    files_changed: list[FileChange],
    root: Path | None = None,
) -> MutationSamplingResult:
    """Apply random mutations to changed production files and check if tests catch them."""
    if root is None:
        root = _repo_root()

    # Only mutate production files (not tests, not configs)
    prod_files = [
        fc
        for fc in files_changed
        if fc.path.endswith(".py")
        and not fc.path.startswith("tests/")
        and not fc.path.startswith("lint/")
        and fc.operation != "delete"
    ]

    if not prod_files:
        return MutationSamplingResult(
            total_mutants=0, killed=0, survived=0, kill_rate=1.0, passed=True
        )

    results: list[MutantResult] = []
    total_budget = _MAX_TOTAL_MUTATIONS

    for fc in prod_files:
        if total_budget <= 0:
            break
        file_path = root / fc.path
        if not file_path.exists():
            continue

        source = file_path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue

        candidates = _find_mutable_lines(tree)
        if not candidates:
            continue

        # Sample up to N mutations per file
        sample_size = min(len(candidates), _MUTATIONS_PER_FILE, total_budget)
        selected = random.sample(candidates, sample_size)

        for line, kind in selected:
            mutated_source, description = _apply_mutation(source, line, kind)
            if mutated_source is None:
                continue

            # Write mutation, run tests, restore
            file_path.write_text(mutated_source, encoding="utf-8")
            try:
                tests_pass = _run_tests(root)
            except subprocess.TimeoutExpired:
                tests_pass = False
            finally:
                file_path.write_text(source, encoding="utf-8")

            survived = tests_pass  # If tests still pass, mutation survived
            results.append(
                MutantResult(
                    file=fc.path,
                    line=line,
                    mutation=description,
                    survived=survived,
                )
            )
            total_budget -= 1

    killed = sum(1 for r in results if not r.survived)
    survived = sum(1 for r in results if r.survived)
    total = len(results)
    kill_rate = killed / max(total, 1)

    return MutationSamplingResult(
        total_mutants=total,
        killed=killed,
        survived=survived,
        kill_rate=kill_rate,
        passed=kill_rate >= _KILL_RATE_THRESHOLD,
        survivors=[r for r in results if r.survived],
    )
