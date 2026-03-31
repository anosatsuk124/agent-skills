"""
Structured error handling with the pattern-matching hint system.
Errors follow the "What + Why + Hint" format.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass


# --- Structured Error ---


@dataclass
class StructuredError(Exception):
    message: str
    why: str | None = None
    hint: str | None = None

    def __str__(self) -> str:
        parts = [f"Error: {self.message}"]
        if self.why:
            parts.append(f"Why:   {self.why}")
        if self.hint:
            parts.append(f"Hint:  {self.hint}")
        return "\n".join(parts)

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"error": self.message}
        if self.why:
            d["why"] = self.why
        if self.hint:
            d["hint"] = self.hint
        return d


# --- Hint Rules ---


@dataclass(frozen=True)
class HintRule:
    pattern: re.Pattern[str]
    hint: str
    command: str | None = None


HINT_RULES: list[HintRule] = [
    HintRule(
        pattern=re.compile(r"not found|does not exist|404", re.IGNORECASE),
        hint='Run `mycli search "<name>"` to find the correct ID.',
    ),
    HintRule(
        pattern=re.compile(r"unauthorized|401|invalid.*token", re.IGNORECASE),
        hint="Run `mycli login` to authenticate.",
    ),
    HintRule(
        pattern=re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE),
        hint="Wait a moment and retry. Use --verbose to see rate limit headers.",
    ),
    HintRule(
        pattern=re.compile(r"forbidden|403|permission", re.IGNORECASE),
        hint="Check that your account has access. Run `mycli whoami` to verify.",
    ),
    HintRule(
        pattern=re.compile(r"invalid.*id|malformed.*id|bad.*uuid", re.IGNORECASE),
        hint='ID format looks wrong. Run `mycli search "<name>"` to find the correct ID.',
    ),
    HintRule(
        pattern=re.compile(r"timeout|timed? ?out|connection.*reset", re.IGNORECASE),
        hint="The request timed out. Check your network connection and retry.",
    ),
    HintRule(
        pattern=re.compile(r"conflict|409|already exists", re.IGNORECASE),
        hint="A resource with this name already exists. Use `mycli update` to modify it.",
    ),
    HintRule(
        pattern=re.compile(r"validation|invalid.*param|missing.*required", re.IGNORECASE),
        hint="Check required parameters with `mycli <command> --help`.",
    ),
]


# --- Hint Matching ---


def find_hint(error: Exception, command: str | None = None) -> str | None:
    """Find the first matching hint for an error message."""
    message = str(error)
    for rule in HINT_RULES:
        if rule.command and rule.command != command:
            continue
        if rule.pattern.search(message):
            return rule.hint
    return None


def enrich_error(error: Exception, command: str | None = None) -> StructuredError:
    """Wrap a plain exception as a StructuredError with a hint."""
    if isinstance(error, StructuredError):
        return error
    hint = find_hint(error, command)
    return StructuredError(message=str(error), hint=hint)


# --- Error Output ---


def print_error(err: StructuredError, *, json_mode: bool = False) -> None:
    """Print a structured error to stderr."""
    if json_mode:
        print(json.dumps(err.to_dict(), indent=2), file=sys.stderr)
    else:
        print(str(err), file=sys.stderr)
