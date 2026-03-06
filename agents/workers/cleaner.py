"""Cleaner (entropy GC) worker — detects entropy violations, returns CleanupOutput."""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.models.cleaner import CleanupOutput
from agents.models.cost import TokenUsage

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "cleaner.txt").read_text()

_agent: Agent[None, CleanupOutput] | None = None  


def _get_agent() -> Agent[None, CleanupOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=CleanupOutput,
            system_prompt=SYSTEM_PROMPT,
            retries=3,
        )
    return _agent


async def run_cleaner(
    scan_report: str, domains: list[str] | None = None
) -> tuple[CleanupOutput, TokenUsage]:
    """Run the cleaner agent. Returns (CleanupOutput, TokenUsage) for cost tracking."""
    with logfire.span("cleaner"):
        domain_list = domains or ["agents", "lint", "repo_index", "tests"]
        prompt = f"""## Lint Scan Report
{scan_report}

## Domains to Score
{", ".join(domain_list)}

Analyze the scan report and produce a CleanupOutput with all violations,
quality scores per domain, recommended PRs for auto-fixable clusters,
and human_review_needed for non-auto-fixable issues.
"""
        agent = _get_agent()
        result = await agent.run(prompt)
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.request_tokens or 0,
            tokens_out=usage_data.response_tokens or 0,
        )
        logfire.info(
            "cleanup_analysis_complete",
            violations_count=len(result.data.violations),
            auto_fixable=sum(1 for v in result.data.violations if v.auto_fixable),
            overall_score=result.data.overall_score(),
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
        )
        return result.data, token_usage
