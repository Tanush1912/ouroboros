"""Planner worker — decomposes a task into typed execution steps.

Returns PlanOutput with structured steps. No free-form text planning.
Has interactive tool access to explore the repo before planning.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.core.context_builder import TaskContext, build_context
from agents.models.cost import TokenUsage
from agents.models.planner import PlanOutput
from agents.tools.tool_wiring import resolve_worker_tools

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "planner.txt").read_text(
    encoding="utf-8"
)

_agent: Agent[None, PlanOutput] | None = None


def _get_agent() -> Agent[None, PlanOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            output_type=PlanOutput,
            system_prompt=SYSTEM_PROMPT,
            tools=resolve_worker_tools("planner"),
            retries=3,
        )
    return _agent


async def run_planner(
    task: str, context: TaskContext | None = None
) -> tuple[PlanOutput, TokenUsage, int]:
    """Run the planner agent. Returns (PlanOutput, TokenUsage, tool_call_count)."""
    if context is None:
        context = build_context(task, worker_role="planner")

    with logfire.span("planner", task=task[:100]):
        agent = _get_agent()
        result = await agent.run(context.to_prompt_text())
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.input_tokens or 0,
            tokens_out=usage_data.output_tokens or 0,
        )
        tool_calls = len(
            [
                m
                for m in result.all_messages()
                if hasattr(m, "parts") and any(hasattr(p, "tool_name") for p in m.parts)
            ]
        )
        logfire.info(
            "plan_created",
            task_summary=result.output.task_summary,
            steps_count=len(result.output.steps),
            risk_level=result.output.risk_level,
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
            tool_calls=tool_calls,
        )
        return result.output, token_usage, tool_calls
