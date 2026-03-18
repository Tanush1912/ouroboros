"""Deterministic behavioral contract verifier — zero LLM cost.

Verifies planner-emitted BehavioralSpecs by executing each check
and returning structured pass/fail results. Each spec kind maps to
a specific verification strategy.
"""

import importlib
import inspect

from agents.core.paths import repo_root as _repo_root
from agents.models.contracts import (
    BehavioralSpec,
    ContractCheckResult,
    ContractVerificationResult,
)


def _check_import(spec: BehavioralSpec) -> ContractCheckResult:
    """Verify a module can be imported."""
    try:
        importlib.import_module(spec.target)
        return ContractCheckResult(
            spec_description=spec.description, passed=True, actual=f"module '{spec.target}' loaded"
        )
    except Exception as e:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual=f"import failed: {type(e).__name__}",
            error=str(e),
        )


def _check_function_exists(spec: BehavioralSpec) -> ContractCheckResult:
    """Verify a function/attribute exists on a module."""
    parts = spec.target.rsplit(".", 1)
    if len(parts) != 2:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual="invalid target format",
            error=f"Expected 'module.name', got '{spec.target}'",
        )
    module_path, attr_name = parts
    try:
        mod = importlib.import_module(module_path)
        if not hasattr(mod, attr_name):
            return ContractCheckResult(
                spec_description=spec.description,
                passed=False,
                actual=f"'{attr_name}' not found in {module_path}",
            )
        obj = getattr(mod, attr_name)
        sig = ""
        if callable(obj):
            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(unknown signature)"
        return ContractCheckResult(
            spec_description=spec.description,
            passed=True,
            actual=f"{attr_name}{sig} exists in {module_path}",
        )
    except Exception as e:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual=f"check failed: {type(e).__name__}",
            error=str(e),
        )


def _check_callable_returns(spec: BehavioralSpec) -> ContractCheckResult:
    """Call a function with args and check the return value/type."""
    parts = spec.target.rsplit(".", 1)
    if len(parts) != 2:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual="invalid target",
            error=f"Expected 'module.function', got '{spec.target}'",
        )
    module_path, func_name = parts
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        # Convert string args to Python values
        args = []
        for a in spec.args:
            try:
                args.append(eval(a))
            except Exception:
                args.append(a)
        result = func(*args)
        actual = repr(result)
        # Check expected — could be a type name or a value
        passed = actual == spec.expected or type(result).__name__ == spec.expected
        return ContractCheckResult(spec_description=spec.description, passed=passed, actual=actual)
    except Exception as e:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual=f"call failed: {type(e).__name__}",
            error=str(e),
        )


def _check_error_raises(spec: BehavioralSpec) -> ContractCheckResult:
    """Call a function with bad input and verify it raises the expected exception."""
    parts = spec.target.rsplit(".", 1)
    if len(parts) != 2:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual="invalid target",
            error=f"Expected 'module.function', got '{spec.target}'",
        )
    module_path, func_name = parts
    try:
        mod = importlib.import_module(module_path)
        func = getattr(mod, func_name)
        args = []
        for a in spec.args:
            try:
                args.append(eval(a))
            except Exception:
                args.append(a)
        try:
            func(*args)
            return ContractCheckResult(
                spec_description=spec.description,
                passed=False,
                actual="no exception raised",
            )
        except Exception as e:
            exc_name = type(e).__name__
            passed = exc_name == spec.expected
            return ContractCheckResult(
                spec_description=spec.description,
                passed=passed,
                actual=f"raised {exc_name}",
                error=None if passed else f"expected {spec.expected}, got {exc_name}",
            )
    except Exception as e:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual=f"setup failed: {type(e).__name__}",
            error=str(e),
        )


def _check_file_exists(spec: BehavioralSpec) -> ContractCheckResult:
    """Verify a file exists at the given path."""
    root = _repo_root()
    path = root / spec.target
    exists = path.exists()
    return ContractCheckResult(
        spec_description=spec.description,
        passed=exists,
        actual=f"{'exists' if exists else 'not found'}: {spec.target}",
    )


def _check_endpoint_returns(spec: BehavioralSpec) -> ContractCheckResult:
    """Check an HTTP endpoint returns the expected status code."""
    try:
        import httpx

        response = httpx.get(spec.target, timeout=5.0)
        actual = str(response.status_code)
        passed = actual == spec.expected
        return ContractCheckResult(
            spec_description=spec.description, passed=passed, actual=f"status {actual}"
        )
    except Exception as e:
        return ContractCheckResult(
            spec_description=spec.description,
            passed=False,
            actual=f"request failed: {type(e).__name__}",
            error=str(e),
        )


_HANDLERS = {
    "import_check": _check_import,
    "function_exists": _check_function_exists,
    "callable_returns": _check_callable_returns,
    "error_raises": _check_error_raises,
    "file_exists": _check_file_exists,
    "endpoint_returns": _check_endpoint_returns,
}


def verify_contracts(specs: list[BehavioralSpec]) -> ContractVerificationResult:
    """Verify all behavioral specs. Returns structured results."""
    if not specs:
        return ContractVerificationResult(passed=True, checks=[], pass_rate=1.0)

    checks = []
    for spec in specs:
        handler = _HANDLERS.get(spec.kind)
        if handler is None:
            checks.append(
                ContractCheckResult(
                    spec_description=spec.description,
                    passed=False,
                    actual=f"unknown spec kind: {spec.kind}",
                )
            )
        else:
            checks.append(handler(spec))

    passed_count = sum(1 for c in checks if c.passed)
    pass_rate = passed_count / len(checks)
    return ContractVerificationResult(
        passed=all(c.passed for c in checks),
        checks=checks,
        pass_rate=pass_rate,
    )
