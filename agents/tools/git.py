"""Git + GitHub PR tools.

All GitHub operations go through the gh CLI. Requires gh to be authenticated.
"""

import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import tool

from agents.core.paths import repo_root as _repo_root


class GitStatus(BaseModel):
    branch: str
    changed_files: list[str] = Field(description="Modified but unstaged files")
    staged_files: list[str] = Field(description="Files staged for commit")
    untracked_files: list[str] = Field(description="New untracked files")
    is_clean: bool = Field(description="True if working tree has no changes")


class CommitResult(BaseModel):
    success: bool
    sha: str = Field(default="", description="Commit SHA if successful")
    message: str = Field(description="Commit message used")
    error: str = Field(default="")


class PRResult(BaseModel):
    success: bool
    url: str = Field(default="")
    number: int = Field(default=0)
    error: str = Field(default="")


class PRComment(BaseModel):
    id: int
    author: str
    body: str
    path: str | None = None
    line: int | None = None
    created_at: str


class MergeResult(BaseModel):
    success: bool
    sha: str = Field(default="", description="Merge commit SHA")
    error: str = Field(default="")


def _run(cmd: list[str]) -> tuple[int, str, str]:
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=_repo_root())
    return result.returncode, result.stdout, result.stderr


@tool
def git_status() -> GitStatus:
    """Returns changed files, staged files, current branch."""
    _, branch_out, _ = _run(["git", "branch", "--show-current"])
    branch = branch_out.strip()

    _, status_out, _ = _run(["git", "status", "--porcelain"])
    changed, staged, untracked = [], [], []
    for line in status_out.splitlines():
        if not line:
            continue
        xy, path = line[:2], line[3:].strip()
        x, y = xy[0], xy[1]
        if x == "?" and y == "?":
            untracked.append(path)
        elif x != " " and x != "?":
            staged.append(path)
        if y == "M" or y == "D":
            changed.append(path)

    return GitStatus(
        branch=branch,
        changed_files=changed,
        staged_files=staged,
        untracked_files=untracked,
        is_clean=not (changed or staged or untracked),
    )


@tool
def commit(message: str, files: list[str]) -> CommitResult:
    """Stage specific files and create a git commit."""
    if not files:
        return CommitResult(success=False, message=message, error="No files specified")

    rc, _, err = _run(["git", "add", "--"] + files)
    if rc != 0:
        return CommitResult(success=False, message=message, error=f"git add failed: {err}")

    rc, out, err = _run(["git", "commit", "-m", message])
    if rc != 0:
        return CommitResult(success=False, message=message, error=f"git commit failed: {err}")

    sha = ""
    for line in out.splitlines():
        if line.startswith("["):
            parts = line.split()
            if len(parts) >= 2:
                sha = parts[1].rstrip("]")
    return CommitResult(success=True, sha=sha, message=message)


@tool
def open_pr(title: str, body: str, base: str = "main") -> PRResult:
    """Open a pull request via gh CLI. Returns PR URL and number."""
    rc, out, err = _run([
        "gh", "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base,
    ])
    if rc != 0:
        return PRResult(success=False, error=err.strip())

    url = out.strip()
    number = 0
    try:
        number = int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        pass
    return PRResult(success=True, url=url, number=number)


@tool
def get_pr_diff(pr_number: int) -> str:
    """Get the full diff for a pull request."""
    rc, out, err = _run(["gh", "pr", "diff", str(pr_number)])
    if rc != 0:
        raise RuntimeError(f"gh pr diff failed: {err}")
    return out


@tool
def get_pr_comments(pr_number: int) -> list[PRComment]:
    """Fetch review comments on a PR. Returns structured comment list."""
    rc, out, err = _run([
        "gh", "api",
        f"repos/:owner/:repo/pulls/{pr_number}/comments",
    ])
    if rc != 0:
        raise RuntimeError(f"gh api failed: {err}")

    raw = json.loads(out)
    return [
        PRComment(
            id=c["id"],
            author=c["user"]["login"],
            body=c["body"],
            path=c.get("path"),
            line=c.get("line"),
            created_at=c["created_at"],
        )
        for c in raw
    ]


@tool
def merge_pr(pr_number: int, strategy: Literal["squash", "merge"] = "squash") -> MergeResult:
    """Merge a pull request."""
    flag = "--squash" if strategy == "squash" else "--merge"
    rc, out, err = _run(["gh", "pr", "merge", str(pr_number), flag, "--auto"])
    if rc != 0:
        return MergeResult(success=False, error=err.strip())
    return MergeResult(success=True)
