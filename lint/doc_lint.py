"""Documentation linter — GP-008: all docs reference real code.

Scans .md files for backtick-quoted paths and symbol names.
Cross-references against the repo index to detect stale references.
"""

import json
import re
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    return Path(result.stdout.strip())


def _load_symbols(root: Path) -> set[str]:
    symbols_path = root / "repo_index" / "symbols.json"
    if not symbols_path.exists():
        return set()
    return set(json.loads(symbols_path.read_text()).keys())


def _load_file_map(root: Path) -> set[str]:
    file_map_path = root / "repo_index" / "file_map.json"
    if not file_map_path.exists():
        return set()
    return set(json.loads(file_map_path.read_text()).keys())


def check_doc_references(doc_path: Path, root: Path, known_files: set[str], known_symbols: set[str]) -> list[str]:
    """Check a single .md file for stale references."""
    content = doc_path.read_text(encoding="utf-8")
    violations = []
    rel_doc = str(doc_path.relative_to(root))

    backtick_refs = re.findall(r"`([^`]+)`", content)

    for ref in backtick_refs:
        if len(ref) < 3 or " " in ref or ref.startswith("$") or "=" in ref:
            continue

        if "/" in ref or ref.endswith(".py") or ref.endswith(".md") or ref.endswith(".json"):
            normalized = ref.lstrip("./")
            if normalized and normalized not in known_files and not (root / normalized).exists():
                violations.append(
                    f"GP-008: {rel_doc} references `{ref}` which does not exist.\n"
                    f"REMEDIATION: Update the reference to the current file location, "
                    f"or remove the reference if the file was deleted."
                )

    return violations


def run_doc_lint(path: str, repo_root: Path | None = None) -> list[str]:
    """Run documentation lint. Returns violation messages."""
    if repo_root is None:
        repo_root = _repo_root()

    known_files = _load_file_map(repo_root)
    known_symbols = _load_symbols(repo_root)

    target = (repo_root / path).resolve()
    if target.is_dir():
        doc_files = list(target.rglob("*.md"))
    elif target.suffix == ".md":
        doc_files = [target]
    else:
        return []

    violations = []
    for doc_file in doc_files:
        violations.extend(check_doc_references(doc_file, repo_root, known_files, known_symbols))

    return violations


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    violations = run_doc_lint(path)

    if violations:
        for v in violations:
            print(v)
            print()
        print(f"Found {len(violations)} documentation violation(s).")
        return 1

    print("Doc lint: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
