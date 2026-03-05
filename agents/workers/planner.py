"""Planner worker — decomposes a task into typed execution steps.

Returns PlanOutput with structured steps. No free-form text planning.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.core.context_builder import TaskContext, build_context
from agents.models.cost import TokenUsage
from agents.models.planner import PlanOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "planner.txt").read_text()

_agent: Agent[None, PlanOutput] | None = None


def _get_agent() -> Agent[None, PlanOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=PlanOutput,
            system_prompt=SYSTEM_PROMPT,
            retries=3,
        )
    return _agent


async def run_planner(
    task: str, context: TaskContext | None = None
) -> tuple[PlanOutput, TokenUsage]:
    """Run the planner agent. Returns (PlanOutput, TokenUsage) for cost tracking."""
    if context is None:
        context = build_context(task)

    with logfire.span("planner", task=task[:100]):
        agent = _get_agent()
        result = await agent.run(context.to_prompt_text())
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.request_tokens or 0,
            tokens_out=usage_data.response_tokens or 0,
        )
        logfire.info(
            "plan_created",
            task_summary=result.data.task_summary,
            steps_count=len(result.data.steps),
            risk_level=result.data.risk_level,
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
        )
        return result.data, token_usage
