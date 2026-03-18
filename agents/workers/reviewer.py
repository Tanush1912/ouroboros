"""Reviewer worker — reviews the PR diff, returns ReviewOutput.

approved=True drives the merge branch in LangGraph. No string parsing.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.models.cost import TokenUsage
from agents.models.reviewer import ReviewOutput
from agents.tools.git import get_pr_diff

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "reviewer.txt").read_text(
    encoding="utf-8"
)

# TODO: Global singleton — not thread-safe for concurrent tasks. Use factory or async-local.
_agent: Agent[None, ReviewOutput] | None = None


def _get_agent() -> Agent[None, ReviewOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            output_type=ReviewOutput,
            system_prompt=SYSTEM_PROMPT,
            retries=3,
        )
    return _agent


async def run_reviewer(pr_number: int, task: str) -> tuple[ReviewOutput, TokenUsage]:
    """Review a PR. Returns (ReviewOutput, TokenUsage) for cost tracking."""
    with logfire.span("reviewer", pr_number=pr_number):
        diff = get_pr_diff(pr_number)

        prompt = f"""## Task Context
{task}

## Pull Request Diff
```diff
{diff[:8000]}
```

Review this PR against the task context and architecture rules.
"""
        agent = _get_agent()
        result = await agent.run(prompt)
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.input_tokens or 0,
            tokens_out=usage_data.output_tokens or 0,
        )
        logfire.info(
            "review_complete",
            pr_number=pr_number,
            approved=result.output.approved,
            blocking_count=len(result.output.blocking_issues),
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
        )
        return result.output, token_usage
