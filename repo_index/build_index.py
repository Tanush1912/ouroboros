"""Repo index builder.

Generates:
  repo_index/symbols.json  — symbol → {file, line, kind}
  repo_index/file_map.json — file → {domain, layer, imports, exports}

Uses:
  - AST parsing for Python files (classes, functions, assignments)
  - ripgrep for fast file discovery
  - ctags as fallback for non-Python files

Run after significant changes or on every CI build:
  python repo_index/build_index.py
"""

import ast
import json
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True
    )
    return Path(result.stdout.strip())


def _discover_python_files(root: Path) -> list[Path]:
    """Find all .py files, excluding virtual envs and build dirs."""
    excluded = {".venv", "venv", "__pycache__", ".git", "dist", "build", ".mypy_cache"}
    files = []
    for f in root.rglob("*.py"):
        parts = set(f.parts)
        if not parts.intersection(excluded):
            files.append(f)
    return sorted(files)


def _extract_symbols(file_path: Path, root: Path) -> list[dict]:
    """Extract symbols from a Python file using AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    rel_path = str(file_path.relative_to(root))
    symbols = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append({
                "name": node.name,
                "file": rel_path,
                "line": node.lineno,
                "kind": "class" if isinstance(node, ast.ClassDef) else "function",
            })
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    symbols.append({
                        "name": target.id,
                        "file": rel_path,
                        "line": node.lineno,
                        "kind": "constant",
                    })

    return symbols


def _extract_imports(file_path: Path) -> list[str]:
    """Extract all import module names from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError:
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return list(set(imports))


def _extract_exports(file_path: Path) -> list[str]:
    """Extract public names defined in a file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except SyntaxError:
        return []

    exports = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                exports.append(node.name)
    return exports


def _infer_domain_layer(rel_path: str) -> tuple[str, str]:
    """Infer domain and layer from file path."""
    parts = rel_path.replace("\\", "/").split("/")
    if len(parts) >= 2:
        domain = parts[0]
        layer = parts[1] if len(parts) > 2 else parts[0]
        return domain, layer
    return parts[0], parts[0]


def build_index(root: Path | None = None) -> tuple[dict, dict]:
    """Build and return (symbols, file_map)."""
    if root is None:
        root = _repo_root()

    py_files = _discover_python_files(root)
    print(f"Indexing {len(py_files)} Python files...")

    symbols: dict[str, dict] = {}
    file_map: dict[str, dict] = {}

    for file_path in py_files:
        rel_path = str(file_path.relative_to(root))

        for sym in _extract_symbols(file_path, root):
            name = sym["name"]
            if name not in symbols or "test" in symbols[name]["file"]:
                symbols[name] = {"file": sym["file"], "line": sym["line"], "kind": sym["kind"]}

        domain, layer = _infer_domain_layer(rel_path)
        file_map[rel_path] = {
            "domain": domain,
            "layer": layer,
            "imports": _extract_imports(file_path),
            "exports": _extract_exports(file_path),
        }

    return symbols, file_map


def main() -> None:
    root = _repo_root()
    index_dir = root / "repo_index"
    index_dir.mkdir(exist_ok=True)

    symbols, file_map = build_index(root)

    symbols_path = index_dir / "symbols.json"
    file_map_path = index_dir / "file_map.json"

    symbols_path.write_text(json.dumps(symbols, indent=2), encoding="utf-8")
    file_map_path.write_text(json.dumps(file_map, indent=2), encoding="utf-8")

    print(f"✓ {len(symbols)} symbols → {symbols_path}")
    print(f"✓ {len(file_map)} files → {file_map_path}")


if __name__ == "__main__":
    main()
