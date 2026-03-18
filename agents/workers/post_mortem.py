"""Post-mortem worker — analyzes failure state, returns HarnessImprovementOutput.

Lightweight agent with no tools. Pure analysis of what went wrong and how
the harness can be improved. Runs after escalation/failure in ralph_loop.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.models.cost import TokenUsage
from agents.models.post_mortem import HarnessImprovementOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "post_mortem.txt").read_text(
    encoding="utf-8"
)

# TODO: Global singleton — not thread-safe for concurrent tasks. Use factory or async-local.
_agent: Agent[None, HarnessImprovementOutput] | None = None


def _get_agent() -> Agent[None, HarnessImprovementOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            output_type=HarnessImprovementOutput,
            system_prompt=SYSTEM_PROMPT,
            retries=2,
        )
    return _agent


def _build_failure_prompt(
    task: str,
    error_log: list[str],
    iteration_count: int,
    review_iteration_count: int,
    estimated_cost_usd: float,
    validation_summary: str | None,
    guard_reasons: list[str],
) -> str:
    """Build a prompt from the failure state for post-mortem analysis."""
    parts = [f"## Original Task\n{task}"]

    parts.append("## Run Statistics")
    parts.append(f"- Implement iterations: {iteration_count}")
    parts.append(f"- Review iterations: {review_iteration_count}")
    parts.append(f"- Estimated cost: ${estimated_cost_usd:.4f}")

    if error_log:
        parts.append("## Error Log")
        for entry in error_log[-20:]:
            parts.append(f"- {entry}")

    if guard_reasons:
        parts.append("## Guard Violations")
        for reason in guard_reasons:
            parts.append(f"- {reason}")

    if validation_summary:
        parts.append(f"## Last Validation Result\n{validation_summary}")

    parts.append(
        "\nAnalyze this failure and recommend a specific harness improvement "
        "to prevent this class of failure from recurring."
    )

    return "\n\n".join(parts)


async def run_post_mortem(
    task: str,
    error_log: list[str],
    iteration_count: int,
    review_iteration_count: int,
    estimated_cost_usd: float,
    validation_summary: str | None = None,
    guard_reasons: list[str] | None = None,
) -> tuple[HarnessImprovementOutput, TokenUsage]:
    """Run post-mortem analysis. Returns (HarnessImprovementOutput, TokenUsage)."""
    with logfire.span("post_mortem", task=task[:100]):
        prompt = _build_failure_prompt(
            task=task,
            error_log=error_log,
            iteration_count=iteration_count,
            review_iteration_count=review_iteration_count,
            estimated_cost_usd=estimated_cost_usd,
            validation_summary=validation_summary,
            guard_reasons=guard_reasons or [],
        )

        agent = _get_agent()
        result = await agent.run(prompt)
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.input_tokens or 0,
            tokens_out=usage_data.output_tokens or 0,
        )

        logfire.info(
            "post_mortem_complete",
            category=result.output.category,
            priority=result.output.priority,
            affected_files=result.output.affected_files,
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
        )
        return result.output, token_usage
