"""Shared test helpers for lint tests."""

import textwrap
from pathlib import Path


def write_py(tmp_path: Path, rel_path: str, content: str) -> Path:
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(content))
    return target
