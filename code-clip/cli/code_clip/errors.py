"""
Structured errors with a hint rule system.
Errors carry What + Why + Hint for self-remediating agent workflows.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Optional


class ClipboardError(Exception):
    """Structured error: What happened + Why + concrete Hint for next step."""

    def __init__(
        self,
        message: str,
        *,
        why: Optional[str] = None,
        hint: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.why = why
        self.hint = hint or _find_hint(message)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"error": str(self)}
        if self.why:
            d["why"] = self.why
        if self.hint:
            d["hint"] = self.hint
        return d

    def __str__(self) -> str:
        parts = [f"Error: {self.args[0]}"]
        if self.why:
            parts.append(f"Why:   {self.why}")
        if self.hint:
            parts.append(f"Hint:  {self.hint}")
        return "\n".join(parts)


@dataclass
class _HintRule:
    pattern: re.Pattern[str]
    hint: str


_HINT_RULES: list[_HintRule] = [
    _HintRule(
        re.compile(r"not found|no such file", re.IGNORECASE),
        "Run `code-clip list --json` to see available clipboard names.",
    ),
    _HintRule(
        re.compile(r"already exists", re.IGNORECASE),
        "Use --overwrite to replace the existing entry, or choose a different name.",
    ),
    _HintRule(
        re.compile(r"stack is empty", re.IGNORECASE),
        "Use `code-clip copy <name> --push` or `code-clip stack push <name>` to push items.",
    ),
    _HintRule(
        re.compile(r"empty.*(name|content)|cannot be empty", re.IGNORECASE),
        "Provide a non-empty value. Pipe content via stdin or use --file.",
    ),
    _HintRule(
        re.compile(r"invalid.*(name|character)", re.IGNORECASE),
        "Names may only contain letters, digits, hyphens, underscores, and dots.",
    ),
    _HintRule(
        re.compile(r"invalid.*line.*range|line.*number", re.IGNORECASE),
        "Specify a line range as 'N' (single line) or 'N-M' (range), e.g. --lines 10-25.",
    ),
    _HintRule(
        re.compile(r"import.*file.*not found", re.IGNORECASE),
        "Provide a valid path to a file created with `code-clip export`.",
    ),
]


def _find_hint(message: str) -> Optional[str]:
    """Match error message against hint rules and return the first matching hint."""
    for rule in _HINT_RULES:
        if rule.pattern.search(message):
            return rule.hint
    return None


def exit_with_error(error: ClipboardError, *, json_mode: bool = False) -> None:
    """Print structured error to stderr and exit with code 1."""
    if json_mode:
        print(json.dumps(error.to_dict()), file=sys.stderr)
    else:
        print(str(error), file=sys.stderr)
    sys.exit(1)
