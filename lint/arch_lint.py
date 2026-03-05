"""Architecture enforcement linter.

Checks layer dependency rules via AST import analysis.
Error messages include AGENT_REMEDIATION fields so agents can self-fix.
"""

import ast
import sys
from pathlib import Path

from agents.core.paths import repo_root as _get_repo_root
from lint.rules import ARCH_RULES, RULES_BY_ID

LAYER_ORDER = ["models", "config", "core", "tools", "workers", "workflows"]

LAYER_MAP = {
    "agents.models": "models",
    "agents.core.config": "config",
    "agents.core": "core",
    "agents.tools": "tools",
    "agents.workers": "workers",
    "agents.workflows": "workflows",
}


def _classify_module(module: str) -> str | None:
    """Return the layer name for a module, or None if not a project module."""
    for prefix, layer in LAYER_MAP.items():
        if module.startswith(prefix):
            return layer
    return None


def _get_imports(file_path: Path) -> list[str]:
    """Return all imported module names from a Python file."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append(node.module)
    return modules


def _file_to_module(rel_path: str) -> str:
    """Convert a relative file path to a dotted module name."""
    return rel_path.replace("/", ".").replace("\\", ".").removesuffix(".py")


def check_file(file_path: Path, repo_root: Path) -> list[str]:
    """Check a single file for architecture violations. Returns violation messages."""
    rel_path = str(file_path.relative_to(repo_root))
    file_module = _file_to_module(rel_path)
    file_layer = _classify_module(file_module)

    if file_layer is None:
        return []  

    violations = []
    imports = _get_imports(file_path)

    for imported in imports:
        imported_layer = _classify_module(imported)
        if imported_layer is None:
            continue

        file_idx = LAYER_ORDER.index(file_layer) if file_layer in LAYER_ORDER else -1
        import_idx = LAYER_ORDER.index(imported_layer) if imported_layer in LAYER_ORDER else -1

        if import_idx > file_idx:
            rule_id = _get_rule_id(file_layer, imported_layer)
            rule = RULES_BY_ID.get(rule_id)
            remediation = rule.agent_remediation if rule else "See ARCHITECTURE.md"
            docs = rule.docs_link if rule else "ARCHITECTURE.md"
            violations.append(
                f"ARCH-VIOLATION: {rel_path} imports from {imported}\n"
                f"RULE: {file_layer.capitalize()} layer cannot import from {imported_layer} layer.\n"
                f"REMEDIATION: {remediation}\n"
                f"DOCS: {docs}"
            )

    if file_layer == "workers":
        for imported in imports:
            if imported.startswith("agents.workers.") and imported != file_module:
                rule = RULES_BY_ID.get("ARCH-001")
                violations.append(
                    f"ARCH-VIOLATION: {rel_path} imports from {imported}\n"
                    f"RULE: Workers cannot cross-import. Extract shared logic to agents/core/.\n"
                    f"REMEDIATION: {rule.agent_remediation if rule else 'Move to agents/core/'}\n"
                    f"DOCS: ARCHITECTURE.md#worker-isolation"
                )

    return violations


def _get_rule_id(file_layer: str, imported_layer: str) -> str:
    if file_layer == "workers" and imported_layer == "workers":
        return "ARCH-001"
    if file_layer == "tools" and imported_layer == "workers":
        return "ARCH-002"
    if file_layer == "models":
        return "ARCH-003"
    return "ARCH-004"


def run_arch_lint(path: str, repo_root: Path | None = None) -> list[str]:
    """Run architecture lint on a path. Returns all violation messages."""
    if repo_root is None:
        repo_root = _get_repo_root()

    target = (repo_root / path).resolve()
    py_files = list(target.rglob("*.py")) if target.is_dir() else [target]

    all_violations = []
    for py_file in py_files:
        all_violations.extend(check_file(py_file, repo_root))

    return all_violations


def main() -> int:
    """CLI entry point."""
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    violations = run_arch_lint(path)

    if violations:
        for v in violations:
            print(v)
            print()
        print(f"Found {len(violations)} architecture violation(s).")
        return 1

    print("Architecture lint: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
