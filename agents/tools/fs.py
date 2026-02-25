"""File system tools for agents.

These tools are the primary interface for reading and writing files.
Agents should prefer search_symbol() over read_file() for navigation.
"""

import json
import os
import subprocess
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_ai import tool


class WriteResult(BaseModel):
    path: str
    bytes_written: int
    created: bool = Field(description="True if file was newly created, False if overwritten")


class SearchMatch(BaseModel):
    file: str
    line: int
    column: int
    text: str = Field(description="The matching line content")


class SymbolLocation(BaseModel):
    name: str
    file: str
    line: int
    kind: str = Field(description="class, function, variable, etc.")


def _repo_root() -> Path:
    """Return the repo root by finding the git root or falling back to cwd."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return Path.cwd()


def _resolve(path: str) -> Path:
    root = _repo_root()
    resolved = (root / path).resolve()
    resolved.relative_to(root.resolve())
    return resolved


@tool
def read_file(path: str) -> str:
    """Read a file from the repository. Returns file contents."""
    return _resolve(path).read_text(encoding="utf-8")


@tool
def write_file(path: str, content: str) -> WriteResult:
    """Write content to a file. Creates parent directories if needed."""
    target = _resolve(path)
    created = not target.exists()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return WriteResult(path=path, bytes_written=len(content.encode()), created=created)


@tool
def list_dir(path: str) -> list[str]:
    """List files and directories at a path."""
    target = _resolve(path)
    if not target.is_dir():
        raise ValueError(f"{path} is not a directory")
    return sorted(str(p.relative_to(_repo_root())) for p in target.iterdir())


@tool
def search_repo(query: str, file_pattern: str = "**/*") -> list[SearchMatch]:
    """Search repository contents using ripgrep. Returns file + line matches."""
    root = _repo_root()
    cmd = [
        "rg", "--json", "--glob", file_pattern,
        query, str(root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    matches = []
    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
            if obj.get("type") == "match":
                data = obj["data"]
                matches.append(SearchMatch(
                    file=str(Path(data["path"]["text"]).relative_to(root)),
                    line=data["line_number"],
                    column=data["submatches"][0]["start"] if data["submatches"] else 0,
                    text=data["lines"]["text"].rstrip(),
                ))
        except (json.JSONDecodeError, KeyError):
            continue
    return matches


@tool
def search_symbol(name: str) -> SymbolLocation | None:
    """Look up a symbol by name. Returns file + line. Never reads the whole repo."""
    symbols_path = _repo_root() / "repo_index" / "symbols.json"
    if not symbols_path.exists():
        return None
    symbols = json.loads(symbols_path.read_text())
    if name in symbols:
        entry = symbols[name]
        return SymbolLocation(
            name=name,
            file=entry["file"],
            line=entry["line"],
            kind=entry["kind"],
        )
    return None
