"""Tool wiring — maps worker roles to PydanticAI-callable tool functions.

Lives in tools layer (legal imports: tools -> models, tools -> tools).
Workers call resolve_worker_tools(role) to get their PydanticAI Agent(tools=[...])
list. This is independent of WORKER_TOOL_ACCESS (which controls what
build_context() shows in the prompt).
"""

from collections.abc import Callable

from agents.core.context_builder import WORKER_TOOL_ACCESS
from agents.tools.fs import list_dir, read_file, search_repo, search_symbol

_NAME_TO_CALLABLE: dict[str, Callable] = {
    "read_file": read_file,
    "list_dir": list_dir,
    "search_repo": search_repo,
    "search_symbol": search_symbol,
}


def resolve_worker_tools(role: str) -> list[Callable]:
    """Return callable tool functions for a worker role.

    Uses WORKER_TOOL_ACCESS to determine which tools are available.
    A role mapped to None gets all tools; a role mapped to a name list
    gets only the tools whose names appear in that list.

    Raises KeyError if role is unknown.
    """
    if role not in WORKER_TOOL_ACCESS:
        raise KeyError(
            f"Unknown worker role '{role}'. Available: {', '.join(sorted(WORKER_TOOL_ACCESS))}"
        )
    allowed_names = WORKER_TOOL_ACCESS[role]
    if allowed_names is None:
        return list(_NAME_TO_CALLABLE.values())
    return [fn for name, fn in _NAME_TO_CALLABLE.items() if name in set(allowed_names)]
