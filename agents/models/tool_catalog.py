"""Tool catalog — type definitions, capability data, and worker access map.

Lives in models layer so both core and tools can import safely.
ToolCapability and ToolRegistry are defined HERE (not in registry.py) to avoid
circular imports. registry.py re-exports them for backward compatibility.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ToolCapability(BaseModel):
    name: str = Field(description="Tool function name (matches @tool decorated function)")
    description: str = Field(description="What the tool does — written for the planner to read")
    input_schema: dict = Field(description="JSON schema of tool inputs")
    output_type: str = Field(description="Python type name of the return value")
    category: Literal[
        "fs", "shell", "git", "browser", "observability", "index", "harness", "benchmark"
    ] = Field(description="Functional category")
    requires_sandbox: bool = Field(
        default=False,
        description="True if this tool requires the Docker sandbox to be running",
    )
    agent_callable: bool = Field(
        default=False,
        description=(
            "True if the planner/implementer agents can call this tool directly "
            "during their PydanticAI run. False means this is a system-level capability "
            "used by workflow orchestration nodes, not by the LLM agent."
        ),
    )


class ToolRegistry:
    """Capability catalog. Instantiated as REGISTRY in agents.models.registry."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolCapability] = {}

    def register(self, tool: ToolCapability) -> None:
        self._tools[tool.name] = tool

    def all_tools(self) -> list[ToolCapability]:
        return list(self._tools.values())

    def tools_for_category(self, category: str) -> list[ToolCapability]:
        return [t for t in self._tools.values() if t.category == category]

    def get_tool(self, name: str) -> ToolCapability | None:
        return self._tools.get(name)

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def agent_callable_tools(self) -> list[ToolCapability]:
        """Return only tools that agents can call directly during their PydanticAI run."""
        return [t for t in self._tools.values() if t.agent_callable]


ALL_TOOL_CAPABILITIES: list[ToolCapability] = [
    # -- File system tools --
    ToolCapability(
        name="read_file",
        description="Read a file from the repository. Returns file contents as string.",
        input_schema={"path": {"type": "string", "description": "Relative path from repo root"}},
        output_type="str",
        category="fs",
        agent_callable=True,
    ),
    ToolCapability(
        name="write_file",
        description="Write content to a file. Creates parent directories if needed.",
        input_schema={
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        output_type="WriteResult",
        category="fs",
    ),
    ToolCapability(
        name="list_dir",
        description="List files and directories at a path.",
        input_schema={"path": {"type": "string"}},
        output_type="list[str]",
        category="fs",
        agent_callable=True,
    ),
    ToolCapability(
        name="search_repo",
        description=(
            "Search repository contents using ripgrep. Returns file + line matches. "
            "Use this instead of reading whole files."
        ),
        input_schema={
            "query": {"type": "string"},
            "file_pattern": {"type": "string", "default": "**/*"},
        },
        output_type="list[SearchMatchResult]",
        category="fs",
        agent_callable=True,
    ),
    # -- Index tools --
    ToolCapability(
        name="search_symbol",
        description=(
            "Look up a symbol (class, function, variable) by name in the repo index. "
            "Returns file + line. Never reads the whole repo. Use this first."
        ),
        input_schema={"name": {"type": "string", "description": "Symbol name to look up"}},
        output_type="SymbolLocationResult | None",
        category="index",
        agent_callable=True,
    ),
    ToolCapability(
        name="reindex",
        description=(
            "Update the repo symbol index for a list of changed file paths. "
            "Call this after write_file so search_symbol stays accurate. "
            "Returns total symbol count."
        ),
        input_schema={
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relative file paths that were written or deleted",
            }
        },
        output_type="int",
        category="index",
    ),
    # -- Shell tools --
    ToolCapability(
        name="run_tests",
        description="Run pytest. Returns structured pass/fail with failure details.",
        input_schema={"path": {"type": "string", "default": "."}},
        output_type="TestResult",
        category="shell",
    ),
    ToolCapability(
        name="run_lint",
        description=(
            "Run ruff + arch_lint + golden_lint. Returns violations with AGENT_REMEDIATION instructions."
        ),
        input_schema={"path": {"type": "string", "default": "."}},
        output_type="LintResult",
        category="shell",
    ),
    ToolCapability(
        name="run_build",
        description="Build the application. Returns success/failure + build log.",
        input_schema={},
        output_type="BuildResult",
        category="shell",
    ),
    ToolCapability(
        name="run_command",
        description="Run an arbitrary shell command. Use sparingly — prefer specific tools.",
        input_schema={
            "command": {"type": "string"},
            "cwd": {"type": "string", "default": "."},
        },
        output_type="CommandResult",
        category="shell",
    ),
    ToolCapability(
        name="run_single_test",
        description="Run a single test file or function with full traceback output for debugging.",
        input_schema={
            "test_path": {"type": "string", "description": "pytest node ID (file::test)"}
        },
        output_type="TestResult",
        category="shell",
    ),
    ToolCapability(
        name="capture_error_context",
        description="Run a command and capture structured error context including Python traceback extraction.",
        input_schema={
            "command": {"type": "string"},
            "cwd": {"type": "string", "default": "."},
        },
        output_type="ErrorContext",
        category="shell",
    ),
    ToolCapability(
        name="run_app_and_probe",
        description="Start app via docker compose and probe the health endpoint. Returns startup status.",
        input_schema={
            "compose_file": {"type": "string", "default": "harness/sandbox/docker-compose.yml"},
            "health_path": {"type": "string", "default": "/health"},
            "timeout_seconds": {"type": "integer", "default": 30},
        },
        output_type="AppStartupResult",
        category="harness",
        requires_sandbox=True,
    ),
    ToolCapability(
        name="probe_endpoint",
        description="Send a single HTTP request to a URL and return structured result with latency.",
        input_schema={
            "url": {"type": "string"},
            "method": {"type": "string", "default": "GET"},
            "expected_status": {"type": "integer", "default": 200},
            "body": {"type": "string"},
        },
        output_type="ProbeResult",
        category="harness",
        requires_sandbox=True,
    ),
    ToolCapability(
        name="run_benchmark",
        description="Run benchmark suite via pytest-benchmark. Returns structured timing results.",
        input_schema={
            "suite_path": {"type": "string", "default": "benchmarks/"},
            "marker": {"type": "string", "default": "benchmark"},
        },
        output_type="BenchmarkResult",
        category="benchmark",
    ),
    ToolCapability(
        name="compare_benchmarks",
        description="Compare two benchmark results and detect regressions above threshold.",
        input_schema={
            "baseline": {"type": "object", "description": "BenchmarkResult baseline"},
            "current": {"type": "object", "description": "BenchmarkResult current"},
            "threshold_pct": {"type": "number", "default": 10.0},
        },
        output_type="PerfComparisonResult",
        category="benchmark",
    ),
    # -- Git tools --
    ToolCapability(
        name="git_status",
        description="Returns changed files, staged files, current branch.",
        input_schema={},
        output_type="GitStatus",
        category="git",
    ),
    ToolCapability(
        name="commit",
        description="Stage specific files and create a git commit.",
        input_schema={
            "message": {"type": "string"},
            "files": {"type": "array", "items": {"type": "string"}},
        },
        output_type="CommitResult",
        category="git",
    ),
    ToolCapability(
        name="open_pr",
        description="Open a pull request via gh CLI. Returns PR URL and number.",
        input_schema={
            "title": {"type": "string"},
            "body": {"type": "string"},
            "base": {"type": "string", "default": "main"},
        },
        output_type="PRResult",
        category="git",
    ),
    ToolCapability(
        name="get_pr_diff",
        description="Get the full diff for a pull request.",
        input_schema={"pr_number": {"type": "integer"}},
        output_type="str",
        category="git",
    ),
    ToolCapability(
        name="get_pr_comments",
        description="Fetch review comments on a PR. Returns structured comment list.",
        input_schema={"pr_number": {"type": "integer"}},
        output_type="list[PRComment]",
        category="git",
    ),
    ToolCapability(
        name="merge_pr",
        description="Merge a pull request.",
        input_schema={
            "pr_number": {"type": "integer"},
            "strategy": {"type": "string", "enum": ["squash", "merge"], "default": "squash"},
        },
        output_type="MergeResult",
        category="git",
    ),
    # -- Browser tools --
    ToolCapability(
        name="take_screenshot",
        description="Navigate to URL and capture screenshot. Returns base64 image.",
        input_schema={"url": {"type": "string"}},
        output_type="ScreenshotResult",
        category="browser",
        requires_sandbox=True,
    ),
    ToolCapability(
        name="snapshot_dom",
        description="Capture DOM accessibility tree. Returns structured DOM for analysis.",
        input_schema={"url": {"type": "string"}},
        output_type="DOMSnapshot",
        category="browser",
        requires_sandbox=True,
    ),
    ToolCapability(
        name="drive_ui_flow",
        description="Execute a sequence of UI actions. Returns pass/fail + screenshots.",
        input_schema={
            "url": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "object"}},
        },
        output_type="UIFlowResult",
        category="browser",
        requires_sandbox=True,
    ),
    # -- Observability tools --
    ToolCapability(
        name="query_logs",
        description=(
            "Query VictoriaLogs with LogQL. "
            'Example: \'{service="api"} |= "error"\'. Duration in Go format (1h, 30m).'
        ),
        input_schema={
            "logql": {"type": "string"},
            "duration": {"type": "string", "default": "1h"},
        },
        output_type="list[LogLineSchema]",
        category="observability",
        requires_sandbox=True,
    ),
    ToolCapability(
        name="query_metrics",
        description=(
            "Query VictoriaMetrics with PromQL. "
            "Example: 'rate(http_requests_total[5m])'. Duration in Go format."
        ),
        input_schema={
            "promql": {"type": "string"},
            "duration": {"type": "string", "default": "1h"},
        },
        output_type="MetricResult",
        category="observability",
        requires_sandbox=True,
    ),
]


def register_all_tools(registry: ToolRegistry) -> None:
    """Register all tool capabilities into the given registry."""
    for tool in ALL_TOOL_CAPABILITIES:
        registry.register(tool)
