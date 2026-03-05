"""Shared path utilities.

Single source of truth for finding the repository root.
Import repo_root from here instead of duplicating _repo_root() across modules.
"""

import subprocess
from pathlib import Path


def repo_root() -> Path:
    """Return the repository root. Falls back to cwd if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return Path.cwd()
