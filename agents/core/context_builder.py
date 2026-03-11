"""Context builder — gatekeeper for token spend.

Agents never receive raw file dumps. build_context(task) produces a TaskContext with
a token budget enforced before the agent sees anything. This prevents context poisoning
and keeps token costs under control.
"""

from pydantic import BaseModel, Field, RootModel

from agents.core.paths import repo_root as _repo_root
from agents.models.registry import REGISTRY
from agents.models.tool_catalog import ALL_TOOL_CAPABILITIES

_JsonDict = RootModel[dict]

_AGENT_CALLABLE_NAMES: list[str] = [t.name for t in ALL_TOOL_CAPABILITIES if t.agent_callable]

WORKER_TOOL_ACCESS: dict[str, list[str] | None] = {
    # None = show ALL tools in context (agent-callable + system). The planner
    # needs full visibility for planning, but can only *call* the 4 tools in
    # _NAME_TO_CALLABLE (read_file, list_dir, search_repo, search_symbol).
    # to_prompt_text() separates "Your Tools" from "System Capabilities".
    "planner": None,
    "implementer": _AGENT_CALLABLE_NAMES,
    "reviewer": [],
    "cleaner": [],
    "post_mortem": [],
}


class FileSnippet(BaseModel):
    path: str
    start_line: int
    end_line: int
    content: str
    relevance_reason: str


class DocReference(BaseModel):
    path: str
    section: str | None = None
    excerpt: str


class ToolSummary(BaseModel):
    name: str
    description: str
    category: str
    agent_callable: bool = False


class TaskContext(BaseModel):
    task: str
    relevant_files: list[FileSnippet] = Field(default_factory=list)
    relevant_docs: list[DocReference] = Field(default_factory=list)
    arch_rules: list[str] = Field(default_factory=list)
    active_plans: list[str] = Field(default_factory=list)
    available_tools: list[ToolSummary] = Field(default_factory=list)
    token_budget_remaining: int

    def to_prompt_text(self) -> str:
        """Render context as a structured prompt string for the agent."""
        parts = [f"## Task\n{self.task}\n"]

        if self.relevant_files:
            parts.append("## Relevant Files")
            for f in self.relevant_files:
                parts.append(f"### {f.path} (lines {f.start_line}-{f.end_line})")
                parts.append(f"_Why relevant: {f.relevance_reason}_")
                parts.append(f"```python\n{f.content}\n```")

        if self.relevant_docs:
            parts.append("## Relevant Documentation")
            for d in self.relevant_docs:
                parts.append(f"### {d.path}" + (f" § {d.section}" if d.section else ""))
                parts.append(d.excerpt)

        if self.arch_rules:
            parts.append("## Architecture Rules (enforced by CI)")
            for rule in self.arch_rules:
                parts.append(f"- {rule}")

        if self.active_plans:
            parts.append("## Active Execution Plans")
            for plan in self.active_plans:
                parts.append(f"- {plan}")

        agent_tools = [t for t in self.available_tools if t.agent_callable]
        system_tools = [t for t in self.available_tools if not t.agent_callable]

        if agent_tools:
            parts.append("## Your Tools (you can call these directly)")
            for t in agent_tools:
                parts.append(f"- `{t.name}` [{t.category}]: {t.description}")

        if system_tools:
            parts.append(
                "## System Capabilities (used by workflow orchestration, not callable by you)"
            )
            for t in system_tools:
                parts.append(f"- `{t.name}` [{t.category}]: {t.description}")

        parts.append(f"\n_Token budget remaining: {self.token_budget_remaining}_")
        return "\n\n".join(parts)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def _load_symbols() -> dict:
    symbols_path = _repo_root() / "repo_index" / "symbols.json"
    if symbols_path.exists():
        return _JsonDict.model_validate_json(symbols_path.read_text(encoding="utf-8")).root
    return {}


def _load_file_map() -> dict:
    file_map_path = _repo_root() / "repo_index" / "file_map.json"
    if file_map_path.exists():
        return _JsonDict.model_validate_json(file_map_path.read_text(encoding="utf-8")).root
    return {}


def _extract_intent_keywords(task: str) -> list[str]:
    """Simple keyword extraction from task string."""
    stopwords = {"the", "a", "an", "in", "at", "to", "for", "and", "or", "of", "is", "it"}
    words = [w.strip(".,()[]\"'").lower() for w in task.split()]
    return [w for w in words if len(w) > 3 and w not in stopwords]


def _find_relevant_files(task: str, file_map: dict, symbols: dict, max_files: int = 5) -> list[str]:
    """Find files relevant to the task using keyword matching against the index."""
    keywords = _extract_intent_keywords(task)
    scored: dict[str, int] = {}

    for file_path, meta in file_map.items():
        score = 0
        for kw in keywords:
            if kw in file_path.lower():
                score += 3
            if kw in meta.get("domain", "").lower():
                score += 2
            for export in meta.get("exports", []):
                if kw in export.lower():
                    score += 2

        if score > 0:
            scored[file_path] = score

    for sym_name, sym_info in symbols.items():
        for kw in keywords:
            if kw in sym_name.lower():
                file = sym_info["file"]
                scored[file] = scored.get(file, 0) + 1

    sorted_files = sorted(scored, key=lambda f: scored[f], reverse=True)
    return sorted_files[:max_files]


def _read_snippet(path: str, max_lines: int = 80) -> FileSnippet | None:
    full_path = _repo_root() / path
    if not full_path.exists():
        return None
    lines = full_path.read_text(encoding="utf-8").splitlines()
    snippet_lines = lines[:max_lines]
    return FileSnippet(
        path=path,
        start_line=1,
        end_line=min(max_lines, len(lines)),
        content="\n".join(snippet_lines),
        relevance_reason="Matched task keywords",
    )


def _load_arch_rules() -> list[str]:
    """Load the key architecture rules from ARCHITECTURE.md."""
    arch_path = _repo_root() / "ARCHITECTURE.md"
    if not arch_path.exists():
        return []
    content = arch_path.read_text(encoding="utf-8")
    rules = []
    in_rules = False
    for line in content.splitlines():
        if "Layer Dependency Rules" in line:
            in_rules = True
        elif in_rules and line.startswith("##"):
            break
        elif in_rules and line.strip() and not line.startswith("#"):
            rules.append(line.strip())
    return rules[:10]


def _load_active_plans() -> list[str]:
    plans_dir = _repo_root() / "docs" / "exec-plans" / "active"
    if not plans_dir.exists():
        return []
    plans = []
    for plan_file in plans_dir.glob("*.md"):
        content = plan_file.read_text(encoding="utf-8")
        first_line = content.splitlines()[0].lstrip("# ").strip() if content else plan_file.name
        plans.append(f"{plan_file.name}: {first_line}")
    return plans


def _discover_doc_files() -> list[str]:
    """Return relative paths for all markdown docs to index."""
    root = _repo_root()
    candidates = [
        "ARCHITECTURE.md",
        "AGENTS.md",
    ]
    docs_dir = root / "docs"
    if docs_dir.exists():
        for md in docs_dir.rglob("*.md"):
            candidates.append(str(md.relative_to(root)))
    return [p for p in candidates if (root / p).exists()]


def _chunk_markdown(path: str) -> list[DocReference]:
    """Split a markdown file into section-level chunks as DocReference objects."""
    full = _repo_root() / path
    if not full.exists():
        return []
    text = full.read_text(encoding="utf-8")
    chunks: list[DocReference] = []
    current_section: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_lines:
                body = "\n".join(current_lines).strip()
                if body:
                    chunks.append(DocReference(path=path, section=current_section, excerpt=body))
            current_section = line.lstrip("# ").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        body = "\n".join(current_lines).strip()
        if body:
            chunks.append(DocReference(path=path, section=current_section, excerpt=body))

    return chunks


def _score_doc_chunk(chunk: DocReference, keywords: list[str]) -> float:
    """Score a doc chunk against task keywords using term frequency."""
    text = f"{chunk.path} {chunk.section or ''} {chunk.excerpt}".lower()
    score = 0.0
    for kw in keywords:
        count = text.count(kw)
        if count:
            score += count
            if chunk.section and kw in chunk.section.lower():
                score += 2.0
    return score


def _find_relevant_docs(task: str, max_docs: int = 3) -> list[DocReference]:
    """Find doc sections relevant to the task using keyword-based TF scoring."""
    keywords = _extract_intent_keywords(task)
    if not keywords:
        return []

    all_chunks: list[DocReference] = []
    for doc_path in _discover_doc_files():
        all_chunks.extend(_chunk_markdown(doc_path))

    scored = [(chunk, _score_doc_chunk(chunk, keywords)) for chunk in all_chunks]
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, _ in scored[:max_docs]]


def build_context(task: str, max_tokens: int = 8000, worker_role: str | None = None) -> TaskContext:
    """
    Build a scoped, budget-aware context package for an agent.

    1. Parse task to extract intent + domain hints
    2. Query repo_index for relevant symbols/files
    3. Pull architecture rules for touched layers
    4. Attach active exec-plans for the domain
    5. Trim everything to fit within max_tokens budget
    """
    budget = max_tokens
    file_map = _load_file_map()
    symbols = _load_symbols()

    relevant_file_paths = _find_relevant_files(task, file_map, symbols)
    relevant_files = []
    for file_path in relevant_file_paths:
        snippet = _read_snippet(file_path)
        if snippet:
            cost = _estimate_tokens(snippet.content)
            if budget - cost > 1000:
                relevant_files.append(snippet)
                budget -= cost

    arch_rules = _load_arch_rules()
    active_plans = _load_active_plans()

    relevant_docs = _find_relevant_docs(task)
    docs_to_include: list[DocReference] = []
    for doc in relevant_docs:
        cost = _estimate_tokens(doc.excerpt)
        if budget - cost > 1000:
            docs_to_include.append(doc)
            budget -= cost

    all_tools = REGISTRY.all_tools()
    if worker_role is not None:
        if worker_role not in WORKER_TOOL_ACCESS:
            available = ", ".join(sorted(WORKER_TOOL_ACCESS.keys()))
            raise KeyError(f"Unknown worker_role '{worker_role}'. Available: {available}")
        allowed_names = WORKER_TOOL_ACCESS[worker_role]
        if allowed_names is not None:
            all_tools = [t for t in all_tools if t.name in set(allowed_names)]
    available_tools = [
        ToolSummary(
            name=t.name,
            description=t.description,
            category=t.category,
            agent_callable=t.agent_callable,
        )
        for t in all_tools
    ]
    tools_token_cost = sum(_estimate_tokens(t.name + t.description) for t in available_tools)
    budget -= tools_token_cost

    return TaskContext(
        task=task,
        relevant_files=relevant_files,
        relevant_docs=docs_to_include,
        arch_rules=arch_rules,
        active_plans=active_plans,
        available_tools=available_tools,
        token_budget_remaining=budget,
    )
