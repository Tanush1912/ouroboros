"""Git + GitHub PR tools.

All GitHub operations go through the gh CLI. Requires gh to be authenticated.
"""

import contextlib
import functools
import json
import subprocess
from typing import Literal

from pydantic import BaseModel, Field

from agents.core.paths import repo_root as _repo_root


@functools.cache
def _repo_nwo() -> str:
    """Return 'owner/repo' for the current repository via gh CLI."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        capture_output=True,
        text=True,
        cwd=_repo_root(),
    )
    nwo = result.stdout.strip()
    if result.returncode != 0 or not nwo:
        raise RuntimeError(f"Failed to resolve owner/repo: {result.stderr.strip()}")
    return nwo


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


_gh_auth_verified = False


def _check_gh_auth() -> None:
    """Verify gh CLI is authenticated. Raises RuntimeError if not. Called once lazily."""
    global _gh_auth_verified
    if _gh_auth_verified:
        return
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "GitHub CLI is not authenticated. Run 'gh auth login' to configure access.\n"
            f"Details: {result.stderr.strip()}"
        )
    _gh_auth_verified = True


def _run(cmd: list[str]) -> tuple[int, str, str]:
    if cmd[0] == "gh":
        _check_gh_auth()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=_repo_root())
    return result.returncode, result.stdout, result.stderr


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


def commit(message: str, files: list[str]) -> CommitResult:
    """Stage specific files and create a git commit."""
    if not files:
        return CommitResult(success=False, message=message, error="No files specified")

    rc, _, err = _run(["git", "add", "--", *files])
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


def open_pr(title: str, body: str, base: str = "main") -> PRResult:
    """Open a pull request via gh CLI. Returns PR URL and number."""
    rc, out, err = _run(
        [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--base",
            base,
        ]
    )
    if rc != 0:
        return PRResult(success=False, error=err.strip())

    url = out.strip()
    number = 0
    with contextlib.suppress(ValueError, IndexError):
        number = int(url.rstrip("/").split("/")[-1])
    return PRResult(success=True, url=url, number=number)


def get_pr_diff(pr_number: int) -> str:
    """Get the full diff for a pull request."""
    rc, out, err = _run(["gh", "pr", "diff", str(pr_number)])
    if rc != 0:
        raise RuntimeError(f"gh pr diff failed: {err}")
    return out


def get_pr_comments(pr_number: int) -> list[PRComment]:
    """Fetch review comments on a PR. Returns structured comment list."""
    rc, out, err = _run(
        [
            "gh",
            "api",
            f"repos/{_repo_nwo()}/pulls/{pr_number}/comments",
        ]
    )
    if rc != 0:
        raise RuntimeError(f"gh api failed: {err}")

    try:
        raw = json.loads(out)
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Failed to parse GitHub API response: {err}") from err
    return [
        PRComment.model_validate(
            {
                "id": c["id"],
                "author": c["user"]["login"],
                "body": c["body"],
                "path": c.get("path"),
                "line": c.get("line"),
                "created_at": c["created_at"],
            }
        )
        for c in raw
    ]


class PRMetadataSchema(BaseModel):
    title: str
    body: str
    branch: str = Field(description="Head branch name")
    base: str = Field(description="Base branch name")
    labels: list[str] = Field(default_factory=list)
    author: str = Field(default="")


class PushResult(BaseModel):
    success: bool
    error: str = Field(default="")


class _PRMetadataRawSchema(BaseModel):
    """Raw GitHub API response schema for PR metadata (GP-004 boundary validation)."""

    model_config = {"populate_by_name": True}

    title: str
    body: str = ""
    head_ref_name: str = Field(alias="headRefName")
    base_ref_name: str = Field(default="main", alias="baseRefName")
    labels: list[dict[str, object]] = Field(default_factory=list)
    author: dict[str, object] = Field(default_factory=dict)


def get_pr_metadata(pr_number: int) -> PRMetadataSchema:
    """Fetch PR title, body, branch, labels, and author via gh CLI."""
    rc, out, err = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "title,body,headRefName,baseRefName,labels,author",
        ]
    )
    if rc != 0:
        raise RuntimeError(f"gh pr view failed: {err}")
    raw = _PRMetadataRawSchema.model_validate_json(out)
    return PRMetadataSchema(
        title=raw.title,
        body=raw.body,
        branch=raw.head_ref_name,
        base=raw.base_ref_name,
        labels=[str(lb.get("name", "")) for lb in raw.labels],
        author=str(raw.author.get("login", "")),
    )


def reply_to_pr_comment(comment_id: int, body: str) -> bool:
    """Reply to a specific PR review comment. Returns True on success."""
    rc, _, _err = _run(
        [
            "gh",
            "api",
            f"repos/{_repo_nwo()}/pulls/comments/{comment_id}/replies",
            "--method",
            "POST",
            "--field",
            f"body={body}",
        ]
    )
    return rc == 0


def add_pr_label(pr_number: int, label: str) -> bool:
    """Add a label to a PR. Creates the label if it doesn't exist."""
    rc, _, _err = _run(["gh", "pr", "edit", str(pr_number), "--add-label", label])
    return rc == 0


def push_to_remote(branch: str) -> PushResult:
    """Push current branch to origin."""
    rc, _, err = _run(["git", "push", "origin", branch])
    if rc != 0:
        return PushResult(success=False, error=err.strip())
    return PushResult(success=True)


class IssueResult(BaseModel):
    success: bool
    url: str = Field(default="")
    number: int = Field(default=0)
    error: str = Field(default="")


def create_issue(title: str, body: str, labels: list[str] | None = None) -> IssueResult:
    """Create a GitHub issue via gh CLI. Returns issue URL and number."""
    cmd = ["gh", "issue", "create", "--title", title, "--body", body]
    for label in labels or []:
        cmd.extend(["--label", label])
    rc, out, err = _run(cmd)
    if rc != 0:
        return IssueResult(success=False, error=err.strip())
    url = out.strip()
    number = 0
    with contextlib.suppress(ValueError, IndexError):
        number = int(url.rstrip("/").split("/")[-1])
    return IssueResult(success=True, url=url, number=number)


def merge_pr(pr_number: int, strategy: Literal["squash", "merge"] = "squash") -> MergeResult:
    """Merge a pull request."""
    flag = "--squash" if strategy == "squash" else "--merge"
    rc, _out, err = _run(["gh", "pr", "merge", str(pr_number), flag, "--auto"])
    if rc != 0:
        return MergeResult(success=False, error=err.strip())
    return MergeResult(success=True)
