"""Validator worker — runs tests and lint, returns ValidationOutput.

The next_action field drives LangGraph conditional routing. No string parsing.
"""

import logfire
from pydantic_ai import Agent

from agents.core.config import get_model
from agents.models.implementer import ImplementOutput
from agents.models.validator import LintResult, TestResult, ValidationOutput
from agents.tools.shell import run_lint, run_tests

SYSTEM_PROMPT = """You are the Validator agent in the Ouroboros system.

Your job is to assess the results of running tests and lint, and determine the next action.

Rules for next_action:
- "proceed": tests pass AND lint passes AND arch_lint passes
- "retry": tests fail OR lint fails, but failures look fixable by the implementer
  (e.g., missing import, off-by-one, lint violation with REMEDIATION instructions)
- "escalate": failures are unrecoverable without human input
  (e.g., missing external dependency, broken infrastructure, unclear requirement)

overall_pass = tests.passed AND lint.passed AND arch_lint.passed

Be conservative with "escalate" — most coding failures should be "retry".
Escalate only when there is no clear mechanical fix the implementer can make.
"""

_agent: Agent[None, ValidationOutput] | None = None


def _get_agent() -> Agent[None, ValidationOutput]:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=get_model(),
            result_type=ValidationOutput,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


async def run_validator(
    implement_output: ImplementOutput,
    iteration: int = 1,
) -> ValidationOutput:
    """Run tests and lint on the implementation, return structured validation result."""
    with logfire.span("validator", iteration=iteration):
        test_result: TestResult = await run_tests.fn(".")  
        lint_result: LintResult = await run_lint.fn(".") 

        arch_violations = [v for v in lint_result.violations if v.startswith("ARCH-")]
        other_violations = [v for v in lint_result.violations if not v.startswith("ARCH-")]

        arch_lint_result = LintResult(
            passed=len(arch_violations) == 0,
            violations=arch_violations,
        )
        ruff_lint_result = LintResult(
            passed=len(other_violations) == 0,
            violations=other_violations,
            auto_fixed=lint_result.auto_fixed,
        )

        overall_pass = test_result.passed and ruff_lint_result.passed and arch_lint_result.passed

        summary_prompt = f"""
Test results: {'PASS' if test_result.passed else 'FAIL'}
Failures: {test_result.failures[:5]}

Lint results: {'PASS' if ruff_lint_result.passed else 'FAIL'}
Violations: {ruff_lint_result.violations[:5]}

Arch lint results: {'PASS' if arch_lint_result.passed else 'FAIL'}
Violations: {arch_lint_result.violations[:3]}

Overall: {'PASS' if overall_pass else 'FAIL'}
Iteration: {iteration}

Files changed: {[f.path for f in implement_output.files_changed]}
Implementation notes: {implement_output.implementation_notes[:500]}

Determine next_action and provide failure_summary if not passing.
"""
        agent = _get_agent()
        result = await agent.run(summary_prompt)
        output = result.data

        final = ValidationOutput(
            tests=test_result,
            lint=ruff_lint_result,
            arch_lint=arch_lint_result,
            overall_pass=overall_pass,
            next_action=output.next_action,
            failure_summary=output.failure_summary,
        )

        logfire.info(
            "validation_complete",
            overall_pass=overall_pass,
            next_action=final.next_action,
            iteration=iteration,
            test_failures=len(test_result.failures),
            lint_violations=len(ruff_lint_result.violations),
        )
        return final
