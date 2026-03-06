"""Tests for golden principle lint rules."""

from pathlib import Path

from lint.golden_lint import (
    check_gp001_duplicates,
    check_gp002_file_size,
    check_gp003_hand_rolled,
    check_gp004_unvalidated_external,
    check_gp005_no_print,
    check_gp006_model_naming,
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
