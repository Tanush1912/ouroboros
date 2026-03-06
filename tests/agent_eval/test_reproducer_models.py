"""Tests for reproducer models — ErrorContext and ReproductionResult."""

from agents.models.reproducer import ErrorContext, ReproductionResult


def test_error_context_construction() -> None:
    ctx = ErrorContext.model_validate(
        {
            "command": "pytest --tb=long -x",
            "returncode": 1,
            "stdout": "collected 10 items",
            "stderr": "FAILED test_foo.py::test_bar",
            "traceback": "Traceback (most recent call last):\n  File ...\nAssertionError",
            "relevant_logs": ["FAILED test_foo.py::test_bar", "AssertionError: expected 1 got 2"],
        }
    )
    assert ctx.returncode == 1
    assert "Traceback" in ctx.traceback
    assert len(ctx.relevant_logs) == 2


def test_error_context_defaults() -> None:
    ctx = ErrorContext(command="ls", returncode=0)
    assert ctx.stdout == ""
    assert ctx.stderr == ""
    assert ctx.traceback == ""
    assert ctx.relevant_logs == []


def test_reproduction_result_reproduced() -> None:
    result = ReproductionResult.model_validate(
        {
            "reproduced": True,
            "steps_attempted": ["pytest --tb=long -x"],
            "error_context": {
                "command": "pytest --tb=long -x",
                "returncode": 1,
                "traceback": "Traceback (most recent call last):\nValueError: bad value",
            },
            "summary": "Bug reproduced via pytest",
        }
    )
    assert result.reproduced is True
    assert result.error_context is not None
    assert "ValueError" in result.error_context.traceback


def test_reproduction_result_not_reproduced() -> None:
    result = ReproductionResult.model_validate(
        {
            "reproduced": False,
            "steps_attempted": ["pytest --tb=long -x"],
            "summary": "Bug not reproduced via pytest",
        }
    )
    assert result.reproduced is False
    assert result.error_context is None


def test_reproduction_result_round_trip() -> None:
    result = ReproductionResult(
        reproduced=True,
        steps_attempted=["pytest -x", "python script.py"],
        error_context=ErrorContext(
            command="pytest -x",
            returncode=1,
            traceback="Traceback ...\nKeyError: 'foo'",
            relevant_logs=["KeyError: 'foo'"],
        ),
        summary="Reproduced",
    )
    data = result.model_dump()
    restored = ReproductionResult.model_validate(data)
    assert restored == result
    assert restored.error_context.relevant_logs == ["KeyError: 'foo'"]
