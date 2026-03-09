"""Documentation linter — GP-008: all docs reference real code.

Scans .md files for backtick-quoted paths and symbol names.
Cross-references against the repo index to detect stale references.
"""

import json
import re
import sys
from pathlib import Path

from agents.core.paths import repo_root as _repo_root


def _load_symbols(root: Path) -> set[str]:
    symbols_path = root / "repo_index" / "symbols.json"
    if not symbols_path.exists():
        return set()
    return set(json.loads(symbols_path.read_text(encoding="utf-8")).keys())


def _load_file_map(root: Path) -> set[str]:
    file_map_path = root / "repo_index" / "file_map.json"
    if not file_map_path.exists():
        return set()
    return set(json.loads(file_map_path.read_text(encoding="utf-8")).keys())


_COMMON_NON_SYMBOLS = {
    "True",
    "False",
    "None",
    "ValueError",
    "TypeError",
    "KeyError",
    "RuntimeError",
    "ImportError",
    "ModuleNotFoundError",
    "Agent",
    "TypedDict",
    "BaseModel",
    "TypeVar",
    "GitHub",
    "Google",
    "Python",
    "Docker",
    "Logfire",
    "LangGraph",
    "StateGraph",
    "PydanticAI",
    "VertexAIModel",
    "VictoriaLogs",
    "VictoriaMetrics",
    "Grafana",
    "Playwright",
    "Vertex",
    "Gemini",
    "OpenTelemetry",
    "FastAPI",
    "PostgreSQL",
    # Acronyms
    "CI",
    "PR",
    "API",
    "GCP",
    "JSON",
    "YAML",
    "TOML",
}


def check_doc_references(
    doc_path: Path, root: Path, known_files: set[str], known_symbols: set[str]
) -> list[str]:
    """Check a single .md file for stale file path and symbol references."""
    content = doc_path.read_text(encoding="utf-8")
    violations = []
    rel_doc = str(doc_path.relative_to(root))

    backtick_refs = re.findall(r"`([^`]+)`", content)

    for ref in backtick_refs:
        if len(ref) < 3 or " " in ref or ref.startswith("$") or "=" in ref:
            continue

        if any(c in ref for c in ("{", "<", "*", "?")):
            continue
        if ref.startswith("/") or ref.startswith(":"):
            continue
        if re.search(r":[^/\d]", ref):
            continue

        if ref.endswith("/"):
            normalized = ref.rstrip("/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            if normalized and "/" in normalized and not (root / normalized).exists():
                violations.append(
                    f"GP-008: {rel_doc} references directory `{ref}` which does not exist.\n"
                    f"REMEDIATION: Update the reference to the current directory location, "
                    f"or remove the reference if the directory was deleted."
                )
            continue
        if "/" in ref:
            normalized = ref
            while normalized.startswith("./"):
                normalized = normalized[2:]
            normalized = re.sub(r":\d+$", "", normalized)
            if normalized and normalized not in known_files and not (root / normalized).exists():
                violations.append(
                    f"GP-008: {rel_doc} references `{ref}` which does not exist.\n"
                    f"REMEDIATION: Update the reference to the current file location, "
                    f"or remove the reference if the file was deleted."
                )
            continue

        if (
            re.match(r"^[A-Z][a-zA-Z0-9]{4,}$", ref)
            and re.search(r"[a-z]", ref)
            and ref not in _COMMON_NON_SYMBOLS
            and known_symbols
            and ref not in known_symbols
        ):
            violations.append(
                f"GP-008: {rel_doc} references symbol `{ref}` which is not in the repo index.\n"
                f"REMEDIATION: Update the reference to the current symbol name, "
                f"or run python repo_index/build_index.py to refresh the index."
            )

    return violations


def run_doc_lint(path: str, repo_root: Path | None = None) -> list[str]:
    """Run documentation lint. Returns violation messages."""
    if repo_root is None:
        repo_root = _repo_root()

    known_files = _load_file_map(repo_root)
    known_symbols = _load_symbols(repo_root)

    _excluded_dirs = {".venv", "venv", ".git", "node_modules", "dist", "build", "__pycache__"}

    target = (repo_root / path).resolve()
    if target.is_dir():
        doc_files = [
            f
            for f in target.rglob("*.md")
            if not _excluded_dirs.intersection(f.relative_to(repo_root).parts)
        ]
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
