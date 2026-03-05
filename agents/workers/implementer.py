"""Implementer worker — writes code based on the plan, returns FileChange[].

Never executes tests or linting — that's the validator's job.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.core.context_builder import TaskContext, build_context
from agents.models.cost import TokenUsage
from agents.models.implementer import ImplementOutput
from agents.models.planner import PlanOutput
from agents.models.validator import ValidationOutput

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "implementer.txt").read_text()

_agent: Agent[None, ImplementOutput] | None = None


def _get_agent() -> Agent[None, ImplementOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=ImplementOutput,
            system_prompt=SYSTEM_PROMPT,
            retries=3,
        )
    return _agent


def _build_prompt(
    task: str,
    plan: PlanOutput,
    context: TaskContext,
    previous_validation: ValidationOutput | None = None,
) -> str:
    parts = [context.to_prompt_text()]
    parts.append("## Execution Plan")
    parts.append(f"**Task:** {plan.task_summary}")
    for i, step in enumerate(plan.steps, 1):
        parts.append(
            f"{i}. [{step.tool}] {step.description}\n"
            f"   Files: {', '.join(step.files_affected)}\n"
            f"   Expected: {step.expected_output}"
        )
    parts.append(f"\n**Test Strategy:** {plan.test_strategy}")

    if previous_validation and not previous_validation.overall_pass:
        parts.append("## Previous Validation Failures — Address All of These")
        if not previous_validation.tests.passed:
            parts.append("### Test Failures")
            for f in previous_validation.tests.failures:
                parts.append(f"- {f}")
        if not previous_validation.lint.passed:
            parts.append("### Lint Violations")
            for v in previous_validation.lint.violations:
                parts.append(f"- {v}")
        if not previous_validation.arch_lint.passed:
            parts.append("### Architecture Violations")
            for v in previous_validation.arch_lint.violations:
                parts.append(f"- {v}")

    return "\n\n".join(parts)


async def run_implementer(
    task: str,
    plan: PlanOutput,
    context: TaskContext | None = None,
    previous_validation: ValidationOutput | None = None,
    iteration: int = 1,
) -> tuple[ImplementOutput, TokenUsage]:
    """Run the implementer agent. Returns (ImplementOutput, TokenUsage) for cost tracking."""
    if context is None:
        context = build_context(task)

    prompt = _build_prompt(task, plan, context, previous_validation)

    with logfire.span("implementer", task=task[:100], iteration=iteration):
        agent = _get_agent()
        result = await agent.run(prompt)
        usage_data = result.usage()
        token_usage = TokenUsage(
            tokens_in=usage_data.request_tokens or 0,
            tokens_out=usage_data.response_tokens or 0,
        )
        logfire.info(
            "implementation_complete",
            files_changed=len(result.data.files_changed),
            iteration=iteration,
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
        )
        return result.data, token_usage
