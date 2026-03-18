"""Test writer worker — writes adversarial tests for the implementer's code.

Separated from the implementer to create an adversarial dynamic.
Has read-only tools — cannot modify production code.
"""

from pathlib import Path

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.core.context_builder import TaskContext, build_context
from agents.models.cost import TokenUsage
from agents.models.implementer import FileChange
from agents.models.planner import PlanOutput
from agents.models.test_quality import TestQualityResult
from agents.models.test_writer import TestWriterOutput
from agents.tools.tool_wiring import resolve_worker_tools

SYSTEM_PROMPT = (Path(__file__).parent.parent / "prompts" / "test_writer.txt").read_text(
    encoding="utf-8"
)

_agent: Agent[None, TestWriterOutput] | None = None


def _get_agent() -> Agent[None, TestWriterOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            output_type=TestWriterOutput,
            system_prompt=SYSTEM_PROMPT,
            tools=resolve_worker_tools("test_writer"),
            retries=3,
        )
    return _agent


def _build_prompt(
    task: str,
    plan: PlanOutput,
    files_changed: list[FileChange],
    context: TaskContext,
    previous_quality: TestQualityResult | None = None,
) -> str:
    parts = [context.to_prompt_text()]
    parts.append("## Task")
    parts.append(plan.task_summary)

    parts.append("## Implementation Files")
    for fc in files_changed:
        if not fc.path.startswith("tests/"):
            parts.append(f"- `{fc.path}` ({fc.operation}): {fc.diff_summary}")

    if plan.behavioral_specs:
        parts.append("## Behavioral Specs (write a test for each)")
        for spec in plan.behavioral_specs:
            parts.append(f"- [{spec.kind}] {spec.description}: {spec.target} → {spec.expected}")

    if previous_quality and not previous_quality.passed:
        parts.append("## Previous Test Quality Issues — Address ALL of These")
        for detail in previous_quality.details:
            parts.append(f"- {detail}")
        if previous_quality.banned_patterns:
            parts.append("### Banned Patterns Found")
            for bp in previous_quality.banned_patterns[:10]:
                parts.append(f"- {bp}")
        if previous_quality.untested_files:
            parts.append("### Untested Production Files")
            for uf in previous_quality.untested_files:
                parts.append(f"- {uf}")

    parts.append(f"\n**Test Strategy:** {plan.test_strategy}")
    return "\n\n".join(parts)


async def run_test_writer(
    task: str,
    plan: PlanOutput,
    files_changed: list[FileChange],
    context: TaskContext | None = None,
    previous_quality: TestQualityResult | None = None,
    iteration: int = 1,
) -> tuple[TestWriterOutput, TokenUsage, int]:
    """Run the test writer agent. Returns (TestWriterOutput, TokenUsage, tool_call_count)."""
    if context is None:
        context = build_context(task, worker_role="test_writer")

    prompt = _build_prompt(task, plan, files_changed, context, previous_quality)

    with logfire.span("test_writer", task=task[:100], iteration=iteration):
        agent = _get_agent()
        result = await agent.run(prompt)
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
            "test_writer_complete",
            test_files=len(result.output.test_files),
            confidence=result.output.confidence,
            iteration=iteration,
            tokens_in=token_usage.tokens_in,
            tokens_out=token_usage.tokens_out,
            tool_calls=tool_calls,
        )
        return result.output, token_usage, tool_calls
