"""
Output layer: handles --json, --raw, and default TTY-aware formatting.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def print_output(
    data: Any,
    *,
    json_mode: bool = False,
    raw: bool = False,
) -> None:
    """Print data to stdout in the appropriate format.

    - raw: pass through exactly as received
    - json_mode: guaranteed parseable JSON (wraps strings in {"text": "..."})
    - default: JSON pretty-print in TTY, clean JSON in pipes
    """
    if raw:
        print(data if isinstance(data, str) else json.dumps(data))
        return

    if json_mode or not sys.stdout.isatty():
        if isinstance(data, str):
            output = json.dumps({"text": data}, indent=2)
        else:
            output = json.dumps(data, indent=2, default=str)
        print(output)
        return

    # Human-friendly TTY output
    _print_pretty(data)


def _print_pretty(data: Any) -> None:
    """Print human-friendly output to the terminal."""
    if isinstance(data, list):
        _print_table(data)
    elif isinstance(data, dict):
        _print_key_value(data)
    else:
        print(data)


def _print_table(rows: list[Any]) -> None:
    """Print a list of dicts as a simple table."""
    if not rows:
        print("(no results)")
        return

    first = rows[0]
    if not isinstance(first, dict):
        for row in rows:
            print(row)
        return

    keys = list(first.keys())
    widths = [
        max(len(k), *(len(str(row.get(k, ""))) for row in rows))
        for k in keys
    ]

    # Header
    print("  ".join(k.ljust(w) for k, w in zip(keys, widths)))
    print("  ".join("─" * w for w in widths))

    # Rows
    for row in rows:
        print("  ".join(str(row.get(k, "")).ljust(w) for k, w in zip(keys, widths)))


def _print_key_value(obj: dict[str, Any]) -> None:
    """Print a dict as aligned key-value pairs."""
    if not obj:
        print("{}")
        return

    max_key_len = max(len(k) for k in obj)
    for key, value in obj.items():
        display = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        print(f"{key.ljust(max_key_len)}  {display}")
