"""Tool Registry — capability catalog for the planner agent.

The planner queries this registry before making a plan. It cannot reference tool names
that don't exist here. When a tool is added, update this registry — the planner
picks it up automatically.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ToolCapability(BaseModel):
    name: str = Field(description="Tool function name (matches @tool decorated function)")
    description: str = Field(description="What the tool does — written for the planner to read")
    input_schema: dict = Field(description="JSON schema of tool inputs")
    output_type: str = Field(description="Python type name of the return value")
    category: Literal["fs", "shell", "git", "browser", "observability", "index"] = Field(
        description="Functional category"
    )
    requires_sandbox: bool = Field(
        default=False,
        description="True if this tool requires the Docker sandbox to be running",
    )


class ToolRegistry:
    """Singleton capability catalog. Query before planning."""

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


REGISTRY = ToolRegistry()

REGISTRY.register(ToolCapability(
    name="read_file",
    description="Read a file from the repository. Returns file contents as string.",
    input_schema={"path": {"type": "string", "description": "Relative path from repo root"}},
    output_type="str",
    category="fs",
))
REGISTRY.register(ToolCapability(
    name="write_file",
    description="Write content to a file. Creates parent directories if needed.",
    input_schema={
        "path": {"type": "string"},
        "content": {"type": "string"},
    },
    output_type="WriteResult",
    category="fs",
))
REGISTRY.register(ToolCapability(
    name="list_dir",
    description="List files and directories at a path.",
    input_schema={"path": {"type": "string"}},
    output_type="list[str]",
    category="fs",
))
REGISTRY.register(ToolCapability(
    name="search_repo",
    description=(
        "Search repository contents using ripgrep. Returns file + line matches. "
        "Use this instead of reading whole files."
    ),
    input_schema={
        "query": {"type": "string"},
        "file_pattern": {"type": "string", "default": "**/*"},
    },
    output_type="list[SearchMatch]",
    category="fs",
))
REGISTRY.register(ToolCapability(
    name="search_symbol",
    description=(
        "Look up a symbol (class, function, variable) by name in the repo index. "
        "Returns file + line. Never reads the whole repo. Use this first."
    ),
    input_schema={"name": {"type": "string", "description": "Symbol name to look up"}},
    output_type="SymbolLocation | None",
    category="index",
))

REGISTRY.register(ToolCapability(
    name="run_tests",
    description="Run pytest. Returns structured pass/fail with failure details.",
    input_schema={"path": {"type": "string", "default": "."}},
    output_type="TestResult",
    category="shell",
))
REGISTRY.register(ToolCapability(
    name="run_lint",
    description=(
        "Run ruff + arch_lint + golden_lint. Returns violations with AGENT_REMEDIATION instructions."
    ),
    input_schema={"path": {"type": "string", "default": "."}},
    output_type="LintResult",
    category="shell",
))
REGISTRY.register(ToolCapability(
    name="run_build",
    description="Build the application. Returns success/failure + build log.",
    input_schema={},
    output_type="BuildResult",
    category="shell",
))
REGISTRY.register(ToolCapability(
    name="run_command",
    description="Run an arbitrary shell command. Use sparingly — prefer specific tools.",
    input_schema={
        "command": {"type": "string"},
        "cwd": {"type": "string", "default": "."},
    },
    output_type="CommandResult",
    category="shell",
))

REGISTRY.register(ToolCapability(
    name="git_status",
    description="Returns changed files, staged files, current branch.",
    input_schema={},
    output_type="GitStatus",
    category="git",
))
REGISTRY.register(ToolCapability(
    name="commit",
    description="Stage specific files and create a git commit.",
    input_schema={
        "message": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
    },
    output_type="CommitResult",
    category="git",
))
REGISTRY.register(ToolCapability(
    name="open_pr",
    description="Open a pull request via gh CLI. Returns PR URL and number.",
    input_schema={
        "title": {"type": "string"},
        "body": {"type": "string"},
        "base": {"type": "string", "default": "main"},
    },
    output_type="PRResult",
    category="git",
))
REGISTRY.register(ToolCapability(
    name="get_pr_diff",
    description="Get the full diff for a pull request.",
    input_schema={"pr_number": {"type": "integer"}},
    output_type="str",
    category="git",
))
REGISTRY.register(ToolCapability(
    name="get_pr_comments",
    description="Fetch review comments on a PR. Returns structured comment list.",
    input_schema={"pr_number": {"type": "integer"}},
    output_type="list[PRComment]",
    category="git",
))
REGISTRY.register(ToolCapability(
    name="merge_pr",
    description="Merge a pull request.",
    input_schema={
        "pr_number": {"type": "integer"},
        "strategy": {"type": "string", "enum": ["squash", "merge"], "default": "squash"},
    },
    output_type="MergeResult",
    category="git",
))

REGISTRY.register(ToolCapability(
    name="take_screenshot",
    description="Navigate to URL and capture screenshot. Returns base64 image.",
    input_schema={"url": {"type": "string"}},
    output_type="ScreenshotResult",
    category="browser",
    requires_sandbox=True,
))
REGISTRY.register(ToolCapability(
    name="snapshot_dom",
    description="Capture DOM accessibility tree. Returns structured DOM for analysis.",
    input_schema={"url": {"type": "string"}},
    output_type="DOMSnapshot",
    category="browser",
    requires_sandbox=True,
))
REGISTRY.register(ToolCapability(
    name="drive_ui_flow",
    description="Execute a sequence of UI actions. Returns pass/fail + screenshots.",
    input_schema={
        "url": {"type": "string"},
        "steps": {"type": "array", "items": {"type": "object"}},
    },
    output_type="UIFlowResult",
    category="browser",
    requires_sandbox=True,
))

REGISTRY.register(ToolCapability(
    name="query_logs",
    description=(
        "Query VictoriaLogs with LogQL. "
        "Example: '{service=\"api\"} |= \"error\"'. Duration in Go format (1h, 30m)."
    ),
    input_schema={
        "logql": {"type": "string"},
        "duration": {"type": "string", "default": "1h"},
    },
    output_type="list[LogLine]",
    category="observability",
    requires_sandbox=True,
))
REGISTRY.register(ToolCapability(
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
))
