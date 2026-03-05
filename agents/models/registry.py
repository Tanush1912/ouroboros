"""Tool capability models and registry singleton.

Lives in agents/models/ so both agents/core/ and agents/tools/ can import it
without violating the layer dependency rules (models → core → tools).
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
