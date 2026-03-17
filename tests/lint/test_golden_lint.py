"""Tests for golden principle lint rules (GP-001 through GP-006, GP-011 through GP-014)."""

from pathlib import Path

from lint.golden_lint import (
    check_gp001_duplicates,
    check_gp002_file_size,
    check_gp003_hand_rolled,
    check_gp004_unvalidated_external,
    check_gp005_no_print,
    check_gp006_model_naming,
)
from lint.golden_lint_ext import (
    check_gp011_cross_module_private_imports,
    check_gp012_file_encoding,
    check_gp013_silent_exception,
    check_gp014_hardcoded_guard_limits,
)
from tests.lint.helpers import write_py


def test_gp002_file_exceeds_500_lines(tmp_path: Path) -> None:
    content = "\n".join(f"x_{i} = {i}" for i in range(510))
    write_py(tmp_path, "agents/core/big_file.py", content)
    violations = check_gp002_file_size(tmp_path)
    assert any("GP-002" in v and "big_file.py" in v for v in violations)


def test_gp002_file_under_limit_passes(tmp_path: Path) -> None:
    content = "\n".join(f"x_{i} = {i}" for i in range(100))
    write_py(tmp_path, "agents/core/small_file.py", content)
    violations = check_gp002_file_size(tmp_path)
    assert violations == []


def test_gp005_print_detected_outside_scripts(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workers/planner.py",
        """
        def run():
            print("hello")
    """,
    )
    violations = check_gp005_no_print(tmp_path)
    assert any("GP-005" in v and "planner.py" in v for v in violations)


def test_gp005_print_allowed_in_scripts(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "scripts/setup.py",
        """
        def main():
            print("Setting up...")
    """,
    )
    violations = check_gp005_no_print(tmp_path)
    assert not any("scripts" in v for v in violations)


def test_gp001_duplicate_function_detected(tmp_path: Path) -> None:
    body = """
        def format_timestamp(ts: float) -> str:
            import datetime
            return datetime.datetime.fromtimestamp(ts).isoformat()
    """
    write_py(tmp_path, "agents/core/utils.py", body)
    write_py(tmp_path, "agents/tools/helpers.py", body)
    violations = check_gp001_duplicates(tmp_path)
    assert any("GP-001" in v for v in violations)


def test_gp001_unique_functions_pass(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/utils.py",
        """
        def compute_hash(s: str) -> str:
            import hashlib
            return hashlib.sha256(s.encode()).hexdigest()
    """,
    )
    write_py(
        tmp_path,
        "agents/tools/helpers.py",
        """
        def slugify(s: str) -> str:
            return s.lower().replace(" ", "-")
    """,
    )
    violations = check_gp001_duplicates(tmp_path)
    assert violations == []


def test_gp003_hand_rolled_retry_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/fetcher.py",
        """
        import time
        def fetch_with_retry(url):
            while True:
                try:
                    return do_fetch(url)
                except Exception:
                    time.sleep(1)
    """,
    )
    violations = check_gp003_hand_rolled(tmp_path)
    assert any("GP-003" in v and "fetch_with_retry" in v for v in violations)


def test_gp003_no_false_positive_on_while_without_sleep(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/processor.py",
        """
        def process_queue(queue):
            while queue:
                item = queue.pop()
                handle(item)
    """,
    )
    violations = check_gp003_hand_rolled(tmp_path)
    assert violations == []


def test_gp004_json_loads_without_validation_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/api_client.py",
        """
        import json
        import subprocess
        def get_status():
            result = subprocess.run(["cmd"], capture_output=True, text=True)
            return json.loads(result.stdout)
    """,
    )
    violations = check_gp004_unvalidated_external(tmp_path)
    assert any("GP-004" in v and "get_status" in v for v in violations)


def test_gp004_json_loads_with_model_validate_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/api_client.py",
        """
        import json
        import subprocess
        def get_status():
            result = subprocess.run(["cmd"], capture_output=True, text=True)
            data = json.loads(result.stdout)
            return StatusModel.model_validate(data)
    """,
    )
    violations = check_gp004_unvalidated_external(tmp_path)
    assert violations == []


def test_gp006_bad_model_name_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/models/planner.py",
        """
        from pydantic import BaseModel
        class PlanData(BaseModel):
            task: str
    """,
    )
    violations = check_gp006_model_naming(tmp_path)
    assert any("GP-006" in v and "PlanData" in v for v in violations)


def test_gp006_approved_suffix_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/models/planner.py",
        """
        from pydantic import BaseModel
        class PlanOutput(BaseModel):
            task: str
    """,
    )
    violations = check_gp006_model_naming(tmp_path)
    assert violations == []


# --- GP-011: No cross-module private imports ---


def test_gp011_cross_module_private_import_detected(tmp_path: Path) -> None:
    write_py(tmp_path, "agents/core/__init__.py", "")
    write_py(tmp_path, "agents/core/utils.py", "def _internal(): pass")
    write_py(
        tmp_path,
        "agents/tools/shell.py",
        """
        from agents.core.utils import _internal
    """,
    )
    violations = check_gp011_cross_module_private_imports(tmp_path)
    assert any("GP-011" in v and "_internal" in v for v in violations)


def test_gp011_same_package_private_import_passes(tmp_path: Path) -> None:
    write_py(tmp_path, "agents/core/__init__.py", "")
    write_py(tmp_path, "agents/core/utils.py", "def _internal(): pass")
    write_py(
        tmp_path,
        "agents/core/helpers.py",
        """
        from agents.core.utils import _internal
    """,
    )
    violations = check_gp011_cross_module_private_imports(tmp_path)
    assert violations == []


# --- GP-012: File encoding ---


def test_gp012_missing_encoding_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/reader.py",
        """
        from pathlib import Path
        def read_config():
            return Path("cfg.txt").read_text()
    """,
    )
    violations = check_gp012_file_encoding(tmp_path)
    assert any("GP-012" in v and "read_text" in v for v in violations)


def test_gp012_with_encoding_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/core/reader.py",
        """
        from pathlib import Path
        def read_config():
            return Path("cfg.txt").read_text(encoding="utf-8")
    """,
    )
    violations = check_gp012_file_encoding(tmp_path)
    assert violations == []


# --- GP-013: No silent exception swallow ---


def test_gp013_silent_swallow_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/tools/fetcher.py",
        """
        def fetch():
            try:
                do_work()
            except Exception:
                return {}
    """,
    )
    violations = check_gp013_silent_exception(tmp_path)
    assert any("GP-013" in v for v in violations)


def test_gp013_logged_exception_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/tools/fetcher.py",
        """
        def fetch():
            try:
                do_work()
            except Exception as e:
                return {"error_log": [str(e)], "status": "failed"}
    """,
    )
    violations = check_gp013_silent_exception(tmp_path)
    assert violations == []


# --- GP-014: No hardcoded guard limits ---


def test_gp014_hardcoded_limit_detected(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workflows/ralph_loop.py",
        """
        async def check_node(state):
            if state["iteration_count"] >= 5:
                return {"status": "escalated"}
    """,
    )
    violations = check_gp014_hardcoded_guard_limits(tmp_path)
    assert any("GP-014" in v and "5" in v for v in violations)


def test_gp014_constant_reference_passes(tmp_path: Path) -> None:
    write_py(
        tmp_path,
        "agents/workflows/ralph_loop.py",
        """
        from agents.core.guards import MAX_IMPLEMENT_ITERATIONS
        async def check_node(state):
            if state["iteration_count"] >= MAX_IMPLEMENT_ITERATIONS:
                return {"status": "escalated"}
    """,
    )
    violations = check_gp014_hardcoded_guard_limits(tmp_path)
    assert violations == []
