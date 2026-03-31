"""
Output formatting: three modes for agent + human use.

  --json   Guaranteed parseable JSON (always)
  --raw    Content only, no metadata wrapping
  default  TTY-smart: pretty table for humans, clean JSON for pipes
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _is_tty() -> bool:
    return sys.stdout.isatty()


def print_result(
    data: Any,
    *,
    json_mode: bool = False,
    raw: bool = False,
) -> None:
    """Print result in the appropriate output mode."""
    if raw:
        _print_raw(data)
    elif json_mode:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif _is_tty():
        _print_pretty(data)
    else:
        # Piped (non-TTY) — clean JSON
        print(json.dumps(data, ensure_ascii=False))


def _print_raw(data: Any) -> None:
    """Output raw content string only."""
    if isinstance(data, dict):
        content = data.get("content") or data.get("diff") or json.dumps(data, ensure_ascii=False)
    else:
        content = str(data)
    # Print without trailing newline if content already ends with one
    if isinstance(content, str) and content.endswith("\n"):
        sys.stdout.write(content)
    else:
        print(content)


def _print_pretty(data: Any) -> None:
    """Human-readable pretty output for TTY."""
    if not isinstance(data, dict):
        print(data)
        return

    # Entry read result (paste / show)
    if "content" in data and "name" in data:
        _print_entry(data)

    # List result
    elif "entries" in data:
        _print_list(data["entries"])

    # Search result
    elif "results" in data:
        _print_list(data["results"], header="Search Results")

    # Diff result
    elif "diff" in data:
        _print_diff(data)

    # Stack list
    elif "stack" in data:
        _print_stack(data["stack"])

    # Verify result
    elif "verified" in data:
        _print_verify(data)

    # Write/delete/clear/merge confirmation
    elif any(k in data for k in ("deleted", "pushed", "imported", "target", "exported_to", "count")):
        _print_confirmation(data)

    else:
        # Fallback: JSON
        print(json.dumps(data, indent=2, ensure_ascii=False))


def _print_entry(data: dict[str, Any]) -> None:
    name = data.get("name", "")
    meta = data.get("metadata", {})
    content = data.get("content", "")

    # Header
    parts = [f"[{name}]"]
    if meta.get("language"):
        parts.append(meta["language"])
    if meta.get("source_file"):
        src = meta["source_file"]
        if meta.get("line_start"):
            src += f":{meta['line_start']}"
            if meta.get("line_end") and meta["line_end"] != meta["line_start"]:
                src += f"-{meta['line_end']}"
        parts.append(src)
    if meta.get("operation") == "cut":
        parts.append("[CUT - remove original]")
    print("  ".join(parts))
    print("-" * 40)
    print(content, end="" if content.endswith("\n") else "\n")
    if meta.get("tags"):
        print(f"Tags: {', '.join(meta['tags'])}")


def _print_list(entries: list[dict[str, Any]], header: str = "Clipboards") -> None:
    if not entries:
        print(f"No {header.lower()} found.")
        return

    print(f"{header} ({len(entries)} entries)")
    print("-" * 60)
    # Column widths
    name_w = max(len(e.get("name", "")) for e in entries)
    name_w = max(name_w, 10)
    for entry in entries:
        name = entry.get("name", "").ljust(name_w)
        lang = (entry.get("language") or "").ljust(12)
        op = entry.get("operation", "copy")
        op_marker = "[CUT]" if op == "cut" else "     "
        lines = str(entry.get("line_count") or "?").rjust(5)
        tags = ", ".join(entry.get("tags", []))
        tag_str = f"  [{tags}]" if tags else ""
        print(f"  {name}  {lang}  {op_marker}  {lines} lines{tag_str}")


def _print_diff(data: dict[str, Any]) -> None:
    name1 = data.get("name1", "")
    name2 = data.get("name2", "")
    diff = data.get("diff", "")
    if not data.get("changed"):
        print(f"No differences between '{name1}' and '{name2}'.")
        return
    print(f"Diff: {name1} -> {name2}")
    print("-" * 40)
    print(diff, end="" if diff.endswith("\n") else "\n")


def _print_stack(stack: list[dict[str, Any]]) -> None:
    if not stack:
        print("Stack is empty.")
        return
    print(f"Stack ({len(stack)} items, top first)")
    print("-" * 40)
    for i, item in enumerate(stack):
        marker = "TOP -> " if i == 0 else "       "
        name = item.get("name", "")
        stale = " [STALE]" if item.get("stale") else ""
        lang = f"  ({item['language']})" if item.get("language") else ""
        lines = f"  {item['line_count']} lines" if item.get("line_count") else ""
        print(f"  {marker}{name}{lang}{lines}{stale}")


def _print_verify(data: dict[str, Any]) -> None:
    name = data.get("name", "")
    verified = data.get("verified")
    reason = data.get("reason", "")
    if verified is True:
        print(f"[OK] '{name}': {reason}")
    elif verified is False:
        print(f"[CHANGED] '{name}': {reason}")
    else:
        print(f"[UNKNOWN] '{name}': {reason}")


def _print_confirmation(data: dict[str, Any]) -> None:
    if "deleted" in data and isinstance(data["deleted"], list):
        count = data.get("count", len(data["deleted"]))
        print(f"Cleared {count} entries.")
    elif "deleted" in data:
        print(f"Deleted '{data['deleted']}'.")
    elif "pushed" in data:
        print(f"Pushed '{data['pushed']}' onto stack (size: {data.get('stack_size', '?')}).")
    elif "imported" in data:
        imported = data.get("imported", [])
        skipped = data.get("skipped", [])
        print(f"Imported {len(imported)} entries.", end="")
        if skipped:
            print(f" Skipped {len(skipped)} (already exist).", end="")
        print()
    elif "target" in data:
        print(f"Merged into '{data['target']}' from {data.get('sources', [])}.")
    elif "exported_to" in data:
        print(f"Exported {data.get('count', '?')} entries to '{data['exported_to']}'.")
    elif "name" in data and "operation" in data:
        op = data["operation"]
        name = data["name"]
        print(f"Saved '{name}' ({op}).")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))
