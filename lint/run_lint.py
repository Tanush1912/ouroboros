"""CLI lint runner — used by CI and agents.

Usage:
  python lint/run_lint.py [path]           # Run all linters
  python lint/run_lint.py --arch-only .   # Architecture lint only
  python lint/run_lint.py --golden-only . # Golden lint only
  python lint/run_lint.py --doc-only .    # Doc lint only
"""

import subprocess
import sys

from agents.core.paths import repo_root as _repo_root


def run_all(path: str) -> int:
    from lint.arch_lint import run_arch_lint
    from lint.doc_lint import run_doc_lint
    from lint.golden_lint import run_golden_lint

    root = _repo_root()
    exit_code = 0

    print("Running ruff...")
    ruff_result = subprocess.run(
        ["python", "-m", "ruff", "check", path], capture_output=True, text=True, cwd=root
    )
    if ruff_result.returncode != 0:
        print(ruff_result.stdout)
        exit_code = 1

    print("Running architecture lint...")
    arch_violations = run_arch_lint(path, root)
    for v in arch_violations:
        print(v)
        print()
    if arch_violations:
        exit_code = 1

    print("Running golden lint...")
    golden_violations = run_golden_lint(path, root)
    for v in golden_violations:
        print(v)
        print()
    if golden_violations:
        exit_code = 1

    print("Running doc lint...")
    doc_violations = run_doc_lint(path, root)
    for v in doc_violations:
        print(v)
        print()
    if doc_violations:
        exit_code = 1

    total = len(arch_violations) + len(golden_violations) + len(doc_violations)
    if exit_code == 0:
        print("\n✓ All lint checks passed.")
    else:
        print(f"\n✗ {total} violation(s) found.")

    return exit_code


def main() -> int:
    args = sys.argv[1:]

    if "--arch-only" in args:
        from lint.arch_lint import run_arch_lint

        path = args[-1] if len(args) > 1 else "."
        violations = run_arch_lint(path)
        for v in violations:
            print(v)
        return 1 if violations else 0

    if "--golden-only" in args:
        from lint.golden_lint import run_golden_lint

        path = args[-1] if len(args) > 1 else "."
        violations = run_golden_lint(path)
        for v in violations:
            print(v)
        return 1 if violations else 0

    if "--doc-only" in args:
        from lint.doc_lint import run_doc_lint

        path = args[-1] if len(args) > 1 else "."
        violations = run_doc_lint(path)
        for v in violations:
            print(v)
        return 1 if violations else 0

    path = args[-1] if args else "."
    return run_all(path)


if __name__ == "__main__":
    sys.exit(main())
