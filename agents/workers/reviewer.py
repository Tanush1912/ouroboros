"""Reviewer worker — reviews the PR diff, returns ReviewOutput.

approved=True drives the merge branch in LangGraph. No string parsing.
"""

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.models.reviewer import ReviewOutput
from agents.tools.git import get_pr_diff

SYSTEM_PROMPT = """You are the Reviewer agent in the Ouroboros system.

Your job is to review a pull request diff and produce a structured review.

Rules:
1. Check for architecture violations (cross-layer imports, worker cross-imports).
2. Check for Golden Principle violations (GP-001 through GP-010).
3. A "blocking" severity comment means approved=False.
4. "major" severity: approved=False unless there are compensating factors.
5. "minor" and "nit": approved=True is still possible.
6. blocking_issues must be populated if approved=False.
7. suggested_fix must be concrete — "refactor this" is not acceptable.
8. arch_violations field: list any ARCH-VIOLATION patterns you detect.

Focus on:
- Correctness and logic errors
- Architecture rule adherence
- Security (no hardcoded secrets, no unvalidated external data)
- Golden Principle compliance
- Code quality (duplication, excessive complexity)

Do NOT flag style issues handled by ruff (formatting, import order).
"""

_agent: Agent[None, ReviewOutput] | None = None


def _get_agent() -> Agent[None, ReviewOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=ReviewOutput,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


async def run_reviewer(pr_number: int, task: str) -> ReviewOutput:
    """Review a PR and return structured ReviewOutput."""
    with logfire.span("reviewer", pr_number=pr_number):
        diff = await get_pr_diff.fn(pr_number)  

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

        logfire.info(
            "review_complete",
            pr_number=pr_number,
            approved=result.data.approved,
            blocking_count=len(result.data.blocking_issues),
            comment_count=len(result.data.comments),
        )
        return result.data
