"""Tests for workflow helpers — path validation and utility functions."""

import pytest

from agents.core.workflow_helpers import apply_file_changes
from agents.models.implementer import FileChange


def test_apply_file_changes_rejects_path_traversal(tmp_path):
    """Path traversal attempts must raise ValueError."""
    changes = [
        FileChange(
            path="../../../etc/passwd",
            operation="create",
            content="hacked",
            diff_summary="path traversal attempt",
        )
    ]
    with pytest.raises(ValueError, match="escapes repository root"):
        apply_file_changes(changes, root=tmp_path)


def test_apply_file_changes_allows_normal_paths(tmp_path):
    """Normal relative paths within the repo should work."""
    changes = [
        FileChange(
            path="agents/core/test_file.py",
            operation="create",
            content="# test",
            diff_summary="create test file",
        )
    ]
    apply_file_changes(changes, root=tmp_path)
    assert (tmp_path / "agents" / "core" / "test_file.py").exists()
    assert (tmp_path / "agents" / "core" / "test_file.py").read_text(encoding="utf-8") == "# test"


def test_apply_file_changes_delete_within_root(tmp_path):
    """Delete operations should also be validated."""
    target = tmp_path / "test.py"
    target.write_text("delete me", encoding="utf-8")
    changes = [
        FileChange(path="test.py", operation="delete", content=None, diff_summary="delete"),
    ]
    apply_file_changes(changes, root=tmp_path)
    assert not target.exists()
