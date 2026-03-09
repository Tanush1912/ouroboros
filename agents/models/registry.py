"""Tool registry singleton and re-exports.

ToolCapability and ToolRegistry are defined in agents/models/tool_catalog.py
(the canonical source). This module re-exports them and creates the REGISTRY
singleton, populated from the tool catalog.
"""

from agents.models.tool_catalog import (
    ToolCapability,
    ToolRegistry,
    register_all_tools,
)

__all__ = ["REGISTRY", "ToolCapability", "ToolRegistry"]

REGISTRY = ToolRegistry()
register_all_tools(REGISTRY)
