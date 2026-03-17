"""Tests for documentation lint — GP-008: docs reference real code."""

from pathlib import Path

from lint.doc_lint import check_doc_references


def _write_md(tmp_path: Path, rel_path: str, content: str) -> Path:
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def test_stale_file_reference_detected(tmp_path: Path) -> None:
    _write_md(
        tmp_path,
        "docs/DESIGN.md",
        "See `agents/core/nonexistent.py` for details.",
    )
    violations = check_doc_references(
        tmp_path / "docs/DESIGN.md",
        root=tmp_path,
        known_files=set(),
        known_symbols=set(),
    )
    assert any("GP-008" in v and "nonexistent.py" in v for v in violations)


def test_valid_file_reference_passes(tmp_path: Path) -> None:
    (tmp_path / "agents" / "core").mkdir(parents=True)
    (tmp_path / "agents" / "core" / "guards.py").write_text("# guards", encoding="utf-8")
    _write_md(
        tmp_path,
        "docs/DESIGN.md",
        "See `agents/core/guards.py` for guard logic.",
    )
    violations = check_doc_references(
        tmp_path / "docs/DESIGN.md",
        root=tmp_path,
        known_files={"agents/core/guards.py"},
        known_symbols=set(),
    )
    assert violations == []


def test_stale_symbol_reference_detected(tmp_path: Path) -> None:
    _write_md(
        tmp_path,
        "docs/DESIGN.md",
        "The `ObsoleteClass` was removed in the refactor.",
    )
    violations = check_doc_references(
        tmp_path / "docs/DESIGN.md",
        root=tmp_path,
        known_files=set(),
        known_symbols={"RalphState", "PlanOutput"},
    )
    assert any("GP-008" in v and "ObsoleteClass" in v for v in violations)


def test_valid_symbol_reference_passes(tmp_path: Path) -> None:
    _write_md(
        tmp_path,
        "docs/DESIGN.md",
        "The `RalphState` TypedDict holds workflow state.",
    )
    violations = check_doc_references(
        tmp_path / "docs/DESIGN.md",
        root=tmp_path,
        known_files=set(),
        known_symbols={"RalphState"},
    )
    assert violations == []


def test_common_non_symbols_not_flagged(tmp_path: Path) -> None:
    _write_md(
        tmp_path,
        "docs/DESIGN.md",
        "Uses `BaseModel` from `Python` standard `TypedDict`.",
    )
    violations = check_doc_references(
        tmp_path / "docs/DESIGN.md",
        root=tmp_path,
        known_files=set(),
        known_symbols={"RalphState"},
    )
    assert violations == []
