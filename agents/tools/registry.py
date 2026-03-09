"""Tool Registry — re-exports from agents.models.registry.

Tool capability registrations now live in agents/models/registry.py alongside
the REGISTRY singleton. This module re-exports for backwards compatibility.
"""

from agents.models.registry import REGISTRY, ToolCapability, ToolRegistry

__all__ = ["REGISTRY", "ToolCapability", "ToolRegistry"]
