"""Ouroboros CLI — entry point for running agent workflows.

Usage:
    ouroboros run "Fix the bug in utils/counter.py"
    ouroboros gc
    ouroboros gc --scores-only
"""

import asyncio
import time

import typer
from rich.console import Console

app = typer.Typer(
    name="ouroboros",
    help="Agent-first software factory — autonomous PR lifecycle.",
    no_args_is_help=True,
)
console = Console(stderr=True)


@app.command()
def run(
    task: str = typer.Argument(..., help="Natural language task description"),
    no_gh: bool = typer.Option(False, "--no-gh", help="Skip GitHub CLI requirement"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress startup banner"),
) -> None:
    """Run the Ralph Loop — plan, implement, validate, review, merge."""
    from agents.core.bootstrap import BootstrapError, bootstrap

    try:
        bootstrap(require_gh=not no_gh, quiet=quiet)
    except BootstrapError as e:
        console.print(f"[red]bootstrap failed:[/red] {e.message}")
        raise typer.Exit(1) from None

    from agents.workflows.ralph_loop import run_ralph_loop

    start = time.monotonic()
    final_state = asyncio.run(run_ralph_loop(task))
    elapsed = time.monotonic() - start

    status = final_state["status"]
    pr_url = final_state.get("pr_url") or ""
    cost = final_state["estimated_cost_usd"]
    tokens_in = final_state["total_tokens_in"]
    tokens_out = final_state["total_tokens_out"]
    iterations = final_state["iteration_count"]

    console.print()
    console.print(f"[bold]status:[/bold]     {status}")
    if pr_url:
        console.print(f"[bold]pr:[/bold]         {pr_url}")
    console.print(f"[bold]cost:[/bold]       ${cost:.4f}")
    console.print(f"[bold]tokens:[/bold]     {tokens_in:,} in / {tokens_out:,} out")
    console.print(f"[bold]iterations:[/bold] {iterations}")
    console.print(f"[bold]duration:[/bold]   {elapsed:.1f}s")

    if status not in ("done", "merged"):
        raise typer.Exit(1)


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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
