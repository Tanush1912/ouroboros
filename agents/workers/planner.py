"""Planner worker — decomposes a task into typed execution steps.

Returns PlanOutput with structured steps. No free-form text planning.
"""

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.core.context_builder import TaskContext, build_context
from agents.models.planner import PlanOutput

SYSTEM_PROMPT = """You are the Planner agent in the Ouroboros system.

Your job is to decompose a task into a typed execution plan.

Rules:
1. Only reference tools that exist in the available_tools list in your context.
2. Each step must name exactly one tool category: fs, shell, git, browser, observability, index.
3. files_affected must list actual file paths, not directories.
4. risk_level = "high" if the task touches agent workflows, guards, or CI configuration.
5. requires_human_review = True if risk_level is "high" OR if the task modifies auth/security.
6. Keep steps atomic — one logical action per step.
7. The test_strategy must reference how the validator will verify success.

You have access to the task context in the user message. Use it to understand
what files exist, what tools are available, and what the architecture rules are.
"""

_agent: Agent[None, PlanOutput] | None = None


def _get_agent() -> Agent[None, PlanOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=PlanOutput,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


async def run_planner(task: str, context: TaskContext | None = None) -> PlanOutput:
    """Run the planner agent and return a typed PlanOutput."""
    if context is None:
        context = build_context(task)

    with logfire.span("planner", task=task[:100]):
        agent = _get_agent()
        result = await agent.run(context.to_prompt_text())
        logfire.info(
            "plan_created",
            task_summary=result.data.task_summary,
            steps_count=len(result.data.steps),
            risk_level=result.data.risk_level,
            requires_human_review=result.data.requires_human_review,
        )
        return result.data
