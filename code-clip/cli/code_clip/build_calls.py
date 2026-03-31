"""
Pure functions that transform CLI arguments into storage operation parameters.
No I/O, no side effects -- easy to test without mocking.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StorageOp:
    """Describes a storage operation without executing it."""
    action: str  # write, read, delete, list, search, diff, clear,
                 # stack_push, stack_pop, stack_list, merge, verify,
                 # batch, export, import_
    params: dict[str, Any]


# Language detection map (extension -> language identifier)
_EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".sql": "sql",
    ".md": "markdown",
    ".mdx": "markdown",
    ".tex": "latex",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".zig": "zig",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".clj": "clojure",
    ".scala": "scala",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
}


def detect_language(file_path: str) -> str | None:
    """Map a file path's extension to a language identifier. Returns None if unknown."""
    from pathlib import Path
    ext = Path(file_path).suffix.lower()
    return _EXT_TO_LANG.get(ext)


def compute_checksum(content: str) -> str:
    """Return 'sha256:<hex>' checksum of content."""
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def parse_line_range(line_spec: str) -> tuple[int, int]:
    """Parse '10-25' -> (10, 25) or '10' -> (10, 10). Raises ValueError on invalid input."""
    line_spec = line_spec.strip()
    if "-" in line_spec:
        parts = line_spec.split("-", 1)
        try:
            start = int(parts[0])
            end = int(parts[1])
        except ValueError:
            raise ValueError(f"Invalid line range '{line_spec}': expected 'N' or 'N-M'")
        if start < 1 or end < start:
            raise ValueError(f"Invalid line range '{line_spec}': start must be >= 1 and end >= start")
        return (start, end)
    else:
        try:
            n = int(line_spec)
        except ValueError:
            raise ValueError(f"Invalid line range '{line_spec}': expected 'N' or 'N-M'")
        if n < 1:
            raise ValueError(f"Invalid line range '{line_spec}': line number must be >= 1")
        return (n, n)


def transform_content(
    content: str,
    *,
    strip_indent: bool = False,
    indent: int | None = None,
) -> str:
    """Pure content transformation for paste operations."""
    if not strip_indent and indent is None:
        return content

    lines = content.splitlines(keepends=True)

    if strip_indent and lines:
        # Find minimum non-empty leading whitespace
        min_indent = None
        for line in lines:
            stripped = line.lstrip()
            if stripped and stripped != "\n":
                leading = len(line) - len(line.lstrip())
                if min_indent is None or leading < min_indent:
                    min_indent = leading
        if min_indent:
            lines = [line[min_indent:] if len(line) > min_indent else line for line in lines]

    if indent is not None:
        prefix = " " * indent
        lines = [prefix + line.lstrip() if line.strip() else line for line in lines]

    return "".join(lines)


# --- Copy ---

def build_copy_call(
    name: str,
    content: str,
    *,
    source_file: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    language: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
    push: bool = False,
) -> StorageOp:
    """Build a storage write operation for copy."""
    resolved_lang = language or (detect_language(source_file) if source_file else None)
    return StorageOp(
        action="write",
        params={
            "name": name,
            "content": content,
            "source_file": source_file,
            "line_start": line_start,
            "line_end": line_end,
            "language": resolved_lang,
            "tags": list(tags) if tags else [],
            "operation": "copy",
            "overwrite": overwrite,
            "push": push,
            "checksum": compute_checksum(content),
        },
    )


# --- Cut ---

def build_cut_call(
    name: str,
    content: str,
    *,
    source_file: str | None = None,
    line_start: int | None = None,
    line_end: int | None = None,
    language: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
) -> StorageOp:
    """Build a storage write operation for cut (same as copy but operation='cut')."""
    resolved_lang = language or (detect_language(source_file) if source_file else None)
    return StorageOp(
        action="write",
        params={
            "name": name,
            "content": content,
            "source_file": source_file,
            "line_start": line_start,
            "line_end": line_end,
            "language": resolved_lang,
            "tags": list(tags) if tags else [],
            "operation": "cut",
            "overwrite": overwrite,
            "push": False,
            "checksum": compute_checksum(content),
        },
    )


# --- Paste ---

def build_paste_call(
    name: str,
    *,
    pop: bool = False,
    strip_indent: bool = False,
    indent: int | None = None,
) -> StorageOp:
    """Build a storage read operation for paste."""
    return StorageOp(
        action="read",
        params={
            "name": name,
            "pop": pop,
            "strip_indent": strip_indent,
            "indent": indent,
        },
    )


# --- List ---

def build_list_call(
    *,
    tag: str | None = None,
    language: str | None = None,
    sort: str = "created",
    limit: int = 50,
) -> StorageOp:
    """Build a list operation for all clipboard entries."""
    return StorageOp(
        action="list",
        params={
            "tag": tag,
            "language": language,
            "sort": sort,
            "limit": limit,
        },
    )


# --- Show ---

def build_show_call(name: str) -> StorageOp:
    """Build a read operation that includes full metadata."""
    return StorageOp(
        action="read",
        params={
            "name": name,
            "pop": False,
            "strip_indent": False,
            "indent": None,
            "include_metadata": True,
        },
    )


# --- Delete ---

def build_delete_call(name: str) -> StorageOp:
    """Build a delete operation for a named clipboard entry."""
    return StorageOp(
        action="delete",
        params={"name": name},
    )


# --- Clear ---

def build_clear_call(*, tag: str | None = None) -> StorageOp:
    """Build a clear operation (all entries, or filtered by tag)."""
    return StorageOp(
        action="clear",
        params={"tag": tag},
    )


# --- Search ---

def build_search_call(
    query: str,
    *,
    scope: str = "all",
    language: str | None = None,
    limit: int = 20,
) -> StorageOp:
    """Build a search operation across clipboard entries."""
    return StorageOp(
        action="search",
        params={
            "query": query,
            "scope": scope,  # "name", "content", "tag", "all"
            "language": language,
            "limit": limit,
        },
    )


# --- Diff ---

def build_diff_call(
    name1: str,
    name2: str,
    *,
    context_lines: int = 3,
) -> StorageOp:
    """Build a diff operation comparing two clipboard entries."""
    return StorageOp(
        action="diff",
        params={
            "name1": name1,
            "name2": name2,
            "context_lines": context_lines,
        },
    )


# --- Stack ---

def build_stack_push_call(name: str) -> StorageOp:
    """Build a stack push operation."""
    return StorageOp(
        action="stack_push",
        params={"name": name},
    )


def build_stack_pop_call(
    *,
    peek: bool = False,
    name: str | None = None,
) -> StorageOp:
    """Build a stack pop (or peek) operation."""
    return StorageOp(
        action="stack_pop",
        params={
            "peek": peek,
            "name": name,
        },
    )


def build_stack_list_call() -> StorageOp:
    """Build a stack list operation."""
    return StorageOp(
        action="stack_list",
        params={},
    )


# --- Merge ---

def build_merge_call(
    target_name: str,
    source_names: list[str],
    *,
    separator: str = "\n",
    delete_sources: bool = False,
) -> StorageOp:
    """Build a merge operation combining multiple clipboard entries."""
    return StorageOp(
        action="merge",
        params={
            "target_name": target_name,
            "source_names": list(source_names),
            "separator": separator,
            "delete_sources": delete_sources,
        },
    )


# --- Verify ---

def build_verify_call(name: str) -> StorageOp:
    """Build a verify operation: re-read source file at recorded lines and compare checksum."""
    return StorageOp(
        action="verify",
        params={"name": name},
    )


# --- Export / Import ---

def build_export_call(*, output_file: str | None = None) -> StorageOp:
    """Build an export operation (serialize entire clipboard state to JSON)."""
    return StorageOp(
        action="export",
        params={"output_file": output_file},
    )


def build_import_call(input_file: str, *, overwrite: bool = False) -> StorageOp:
    """Build an import operation (restore clipboard state from JSON)."""
    return StorageOp(
        action="import_",
        params={
            "input_file": input_file,
            "overwrite": overwrite,
        },
    )
