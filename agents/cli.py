"""Ouroboros CLI — entry point for running agent workflows.

Usage:
    ouroboros run "Fix the bug in utils/counter.py"
    ouroboros run --worktree "Fix the bug"  # isolated worktree
    ouroboros status                         # list active runs
    ouroboros gc
    ouroboros gc --scores-only
"""

import asyncio
import hashlib
import os
import subprocess
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="ouroboros",
    help="Agent-first software factory — autonomous PR lifecycle.",
    no_args_is_help=True,
)
console = Console(stderr=True)

_BRANCH_PREFIX = "ouroboros/task-"


def _task_branch_name(task: str) -> str:
    """Generate a unique branch name from a task string."""
    short_hash = hashlib.sha256(f"{task}{time.time()}".encode()).hexdigest()[:8]
    return f"{_BRANCH_PREFIX}{short_hash}"


def _create_worktree(branch: str) -> Path:
    """Create a git worktree for isolated execution. Returns the worktree path."""
    repo_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    worktree_path = Path(repo_root).parent / f"project-ouroboros-{branch.replace('/', '-')}"

    subprocess.run(
        ["git", "worktree", "add", str(worktree_path), "-b", branch],
        check=True,
        capture_output=True,
        text=True,
    )
    return worktree_path


def _cleanup_worktree(worktree_path: Path, branch: str) -> None:
    """Remove a git worktree and its branch."""
    original_dir = os.getcwd()
    try:
        os.chdir(original_dir)
        subprocess.run(
            ["git", "worktree", "remove", str(worktree_path), "--force"],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "branch", "-D", branch],
            capture_output=True,
            text=True,
        )
    except Exception as e:
        console.print(f"[yellow]worktree cleanup failed:[/yellow] {e}")


@app.command()
def run(
    task: str = typer.Argument(..., help="Natural language task description"),
    no_gh: bool = typer.Option(False, "--no-gh", help="Skip GitHub CLI requirement"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress startup banner"),
    worktree: bool = typer.Option(
        False, "--worktree", "-w", help="Run in an isolated git worktree"
    ),
) -> None:
    """Run the Ralph Loop — plan, implement, validate, review, merge."""
    from agents.core.bootstrap import BootstrapError, bootstrap

    try:
        bootstrap(require_gh=not no_gh, quiet=quiet)
    except BootstrapError as e:
        console.print(f"[red]bootstrap failed:[/red] {e.message}")
        raise typer.Exit(1) from None

    worktree_path: Path | None = None
    branch: str | None = None
    original_dir = os.getcwd()
    final_state: dict | None = None

    if worktree:
        branch = _task_branch_name(task)
        try:
            worktree_path = _create_worktree(branch)
        except subprocess.CalledProcessError as e:
            console.print(f"[red]worktree creation failed:[/red] {e.stderr}")
            raise typer.Exit(1) from None
        os.chdir(worktree_path)
        console.print(f"[dim]worktree:[/dim] {worktree_path}")
        console.print(f"[dim]branch:[/dim]   {branch}")

    try:
        from agents.workflows.ralph_loop import run_ralph_loop

        start = time.monotonic()
        final_state = asyncio.run(run_ralph_loop(task))
        elapsed = time.monotonic() - start

        run_status = final_state["status"]
        pr_url = final_state.get("pr_url") or ""
        cost = final_state["estimated_cost_usd"]
        tokens_in = final_state["total_tokens_in"]
        tokens_out = final_state["total_tokens_out"]
        iterations = final_state["iteration_count"]

        console.print()
        console.print(f"[bold]status:[/bold]     {run_status}")
        if pr_url:
            console.print(f"[bold]pr:[/bold]         {pr_url}")
        console.print(f"[bold]cost:[/bold]       ${cost:.4f}")
        console.print(f"[bold]tokens:[/bold]     {tokens_in:,} in / {tokens_out:,} out")
        console.print(f"[bold]iterations:[/bold] {iterations}")
        console.print(f"[bold]duration:[/bold]   {elapsed:.1f}s")
        if branch:
            console.print(f"[bold]branch:[/bold]     {branch}")

        if run_status not in ("done", "merged"):
            raise typer.Exit(1)
    finally:
        if worktree_path:
            os.chdir(original_dir)
            if final_state and final_state.get("status") in ("done", "merged"):
                subprocess.run(
                    ["git", "-C", str(worktree_path), "push", "-u", "origin", branch],
                    capture_output=True,
                    text=True,
                )
            _cleanup_worktree(worktree_path, branch)


@app.command()
def gc(
    scores_only: bool = typer.Option(
        False, "--scores-only", help="Only update quality scores, skip PR creation"
    ),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress startup banner"),
) -> None:
    """Run the Entropy GC workflow — scan, cleanup, update quality scores."""
    from agents.core.bootstrap import BootstrapError, bootstrap

    try:
        bootstrap(require_gh=not scores_only, quiet=quiet)
    except BootstrapError as e:
        console.print(f"[red]bootstrap failed:[/red] {e.message}")
        raise typer.Exit(1) from None

    from agents.workflows.entropy_gc import run_entropy_gc

    final_state = asyncio.run(run_entropy_gc(update_scores_only=scores_only))

    cleanup = final_state.get("cleanup")
    prs = final_state.get("prs_opened", [])

    console.print()
    if cleanup:
        console.print(f"[bold]violations:[/bold]  {len(cleanup.violations)}")
        console.print(f"[bold]score:[/bold]       {cleanup.overall_score():.1f}/10")
    console.print(f"[bold]PRs opened:[/bold]  {len(prs)}")
    for url in prs:
        console.print(f"  {url}")
    console.print(
        f"[bold]quality score updated:[/bold] {final_state.get('quality_score_updated', False)}"
    )


_MAX_FEEDBACK_ITERATIONS = 3


@app.command()
def feedback(
    pr_number: int = typer.Argument(..., help="PR number to address feedback on"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress startup banner"),
) -> None:
    """Address human review comments on an agent PR — implement fixes, push, reply."""
    from agents.core.bootstrap import BootstrapError, bootstrap

    try:
        bootstrap(require_gh=True, quiet=quiet)
    except BootstrapError as e:
        console.print(f"[red]bootstrap failed:[/red] {e.message}")
        raise typer.Exit(1) from None

    from agents.tools.git import add_pr_label, get_pr_comments, get_pr_metadata

    try:
        meta = get_pr_metadata(pr_number)
    except RuntimeError as e:
        console.print(f"[red]Failed to fetch PR #{pr_number}:[/red] {e}")
        raise typer.Exit(1) from None

    if not meta.branch.startswith(_BRANCH_PREFIX):
        console.print(
            f"[red]PR #{pr_number} branch '{meta.branch}' is not an agent PR "
            f"(expected prefix '{_BRANCH_PREFIX}').[/red]"
        )
        raise typer.Exit(1)

    feedback_labels = [lb for lb in meta.labels if lb.startswith("feedback-iteration-")]
    iteration_number = len(feedback_labels) + 1
    if iteration_number > _MAX_FEEDBACK_ITERATIONS:
        console.print(
            f"[red]PR #{pr_number} has reached max feedback iterations "
            f"({_MAX_FEEDBACK_ITERATIONS}). Escalate to a human.[/red]"
        )
        raise typer.Exit(1)

    try:
        comments = get_pr_comments.fn(pr_number)
    except RuntimeError as e:
        console.print(f"[red]Failed to fetch PR comments:[/red] {e}")
        raise typer.Exit(1) from None

    if not comments:
        console.print(f"[yellow]No review comments found on PR #{pr_number}.[/yellow]")
        raise typer.Exit(0)

    comment_dicts = [c.model_dump() for c in comments]

    task_section = meta.body.split("## Task\n", 1)
    original_task = task_section[1].split("\n\n", 1)[0] if len(task_section) > 1 else meta.title

    console.print(f"[dim]PR:[/dim]        #{pr_number} — {meta.title}")
    console.print(f"[dim]branch:[/dim]    {meta.branch}")
    console.print(f"[dim]comments:[/dim]  {len(comments)}")
    console.print(f"[dim]iteration:[/dim] {iteration_number}/{_MAX_FEEDBACK_ITERATIONS}")

    checkout_result = subprocess.run(
        ["git", "checkout", meta.branch],
        capture_output=True,
        text=True,
    )
    if checkout_result.returncode != 0:
        subprocess.run(
            ["git", "fetch", "origin", meta.branch],
            capture_output=True,
            text=True,
        )
        checkout_result = subprocess.run(
            ["git", "checkout", meta.branch],
            capture_output=True,
            text=True,
        )
        if checkout_result.returncode != 0:
            console.print(
                f"[red]Failed to checkout branch {meta.branch}:[/red] {checkout_result.stderr}"
            )
            raise typer.Exit(1)

    subprocess.run(
        ["git", "pull", "origin", meta.branch],
        capture_output=True,
        text=True,
    )

    from agents.workflows.feedback_loop import run_feedback_loop

    start = time.monotonic()
    final_state = asyncio.run(
        run_feedback_loop(
            pr_number=pr_number,
            pr_branch=meta.branch,
            original_task=original_task,
            feedback_comments=comment_dicts,
        )
    )
    elapsed = time.monotonic() - start

    run_status = final_state["status"]
    cost = final_state["estimated_cost_usd"]
    tokens_in = final_state["total_tokens_in"]
    tokens_out = final_state["total_tokens_out"]
    iterations = final_state["iteration_count"]

    console.print()
    console.print(f"[bold]status:[/bold]     {run_status}")
    console.print(f"[bold]cost:[/bold]       ${cost:.4f}")
    console.print(f"[bold]tokens:[/bold]     {tokens_in:,} in / {tokens_out:,} out")
    console.print(f"[bold]iterations:[/bold] {iterations}")
    console.print(f"[bold]duration:[/bold]   {elapsed:.1f}s")

    if run_status == "done":
        add_pr_label(pr_number, f"feedback-iteration-{iteration_number}")

    if run_status not in ("done",):
        raise typer.Exit(1)


@app.command()
def status() -> None:
    """List active ouroboros worktrees and their branches."""
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        console.print("[red]Failed to list worktrees[/red]")
        raise typer.Exit(1)

    worktrees: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line.split(" ", 1)[1]}
        elif line.startswith("branch "):
            current["branch"] = line.split(" ", 1)[1].replace("refs/heads/", "")
        elif line == "":
            if current:
                worktrees.append(current)
            current = {}
    if current:
        worktrees.append(current)

    agent_worktrees = [w for w in worktrees if w.get("branch", "").startswith(_BRANCH_PREFIX)]

    if not agent_worktrees:
        console.print("No active ouroboros worktrees.")
        return

    table = Table(title="Active Ouroboros Worktrees")
    table.add_column("Branch", style="cyan")
    table.add_column("Path", style="dim")
    for w in agent_worktrees:
        table.add_row(w.get("branch", ""), w.get("path", ""))
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
