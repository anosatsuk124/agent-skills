# Error Handling and Hint System

How to implement structured error messages with the pattern-matching hint
system. Read this when implementing the error layer.

---

## The "What + Why + Hint" Format

Every error must answer three questions:

```
Error: <what failed>           -- the symptom
Why:   <root cause>            -- why it happened
Hint:  <concrete next step>    -- what to do about it
```

The `Why` and `Hint` fields are optional but strongly encouraged. An error
without a hint forces the agent (or human) to guess what to do next. An error
with a hint is self-remediating -- the agent can follow the suggestion
automatically.

---

## StructuredError Type

### TypeScript

```typescript
class StructuredError extends Error {
  readonly why?: string;
  readonly hint?: string;

  constructor(message: string, opts?: { why?: string; hint?: string }) {
    super(message);
    this.name = "StructuredError";
    this.why = opts?.why;
    this.hint = opts?.hint;
  }

  toJSON() {
    return {
      error: this.message,
      ...(this.why && { why: this.why }),
      ...(this.hint && { hint: this.hint }),
    };
  }
}
```

### Python

```python
from dataclasses import dataclass

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

    def to_dict(self) -> dict:
        d = {"error": self.message}
        if self.why:
            d["why"] = self.why
        if self.hint:
            d["hint"] = self.hint
        return d
```

---

## The Hint Rule System

Instead of embedding hints in every error path, maintain a centralized array
of hint rules. Each rule has a regex pattern that matches against error
messages and produces a hint.

### HintRule Type

```typescript
interface HintRule {
  /** Regex pattern to match against the error message */
  pattern: RegExp;
  /** Optional: only apply to errors from specific commands */
  command?: string;
  /** The hint to show when this pattern matches */
  hint: string;
}
```

### Hint Rule Registry

```typescript
const HINT_RULES: HintRule[] = [
  {
    pattern: /not found|does not exist|404/i,
    hint: 'Run `mycli search "<name>"` to find the correct ID.',
  },
  {
    pattern: /unauthorized|401|invalid.*token/i,
    hint: "Run `mycli login` to authenticate.",
  },
  {
    pattern: /rate.?limit|429|too many requests/i,
    hint: "Wait a moment and retry. Use --verbose to see rate limit headers.",
  },
  {
    pattern: /forbidden|403|permission/i,
    hint: "Check that your account has access to this resource. Run `mycli whoami` to verify your identity.",
  },
  {
    pattern: /invalid.*id|malformed.*id|bad.*uuid/i,
    hint: 'The ID format looks wrong. Run `mycli search "<name>"` to find the correct ID.',
  },
  {
    pattern: /timeout|ETIMEDOUT|ECONNRESET/i,
    hint: "The request timed out. Check your network connection and retry.",
  },
  {
    pattern: /conflict|409|already exists/i,
    hint: "A resource with this name already exists. Use `mycli update` to modify it, or choose a different name.",
  },
  {
    pattern: /validation|invalid.*param|missing.*required/i,
    hint: "Check required parameters with `mycli <command> --help`.",
  },
];
```

### Finding and Applying Hints

```typescript
function findHint(error: Error, command?: string): string | undefined {
  const message = error.message;
  for (const rule of HINT_RULES) {
    if (rule.command && rule.command !== command) continue;
    if (rule.pattern.test(message)) return rule.hint;
  }
  return undefined;
}

function enrichError(error: Error, command?: string): StructuredError {
  if (error instanceof StructuredError) return error;
  const hint = findHint(error, command);
  return new StructuredError(error.message, { hint });
}
```

### Python equivalent

```python
import re
from dataclasses import dataclass

@dataclass
class HintRule:
    pattern: re.Pattern
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
    # ... more rules
]

def find_hint(error: Exception, command: str | None = None) -> str | None:
    message = str(error)
    for rule in HINT_RULES:
        if rule.command and rule.command != command:
            continue
        if rule.pattern.search(message):
            return rule.hint
    return None
```

---

## Error Output Format

### Human (TTY) mode

```
Error: Could not find page with ID "abc123"
Why:   The page may have been deleted or the ID is incorrect
Hint:  Run `mycli search "page title"` to find the correct page ID
```

### JSON mode (`--json`)

```json
{
  "error": "Could not find page with ID \"abc123\"",
  "why": "The page may have been deleted or the ID is incorrect",
  "hint": "Run `mycli search \"page title\"` to find the correct page ID"
}
```

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error (API error, validation error) |
| 2 | Usage error (invalid arguments, missing required flags) |
| 3 | Authentication error (not logged in, expired token) |

Consistent exit codes let agents branch on error type without parsing messages.

---

## Error Wrapping Pattern

Wrap upstream errors to add context as they propagate up:

```typescript
async function executeCommand(
  command: string,
  buildCall: () => ApiCall,
  opts: OutputOptions
): Promise<void> {
  try {
    const call = buildCall();
    const result = await withConnection((client) => client.execute(call));
    printOutput(result, opts);
  } catch (error) {
    const structured = enrichError(error as Error, command);
    printError(structured, opts);
  }
}
```

This pattern ensures:
1. `buildCall()` errors get hints (e.g., validation failures)
2. Network errors get hints (e.g., timeout, connection reset)
3. API errors get hints (e.g., 404, 401, 429)
4. All errors are formatted consistently

---

## Extending Hints

When users report common errors that lack good hints, add a new rule to the
`HINT_RULES` array. The pattern-matching system makes this trivial -- no code
changes to error handling logic, just a new entry in the array.

Good hint rules are:
- **Specific**: Match a narrow error pattern, not broad categories
- **Actionable**: Tell the user exactly what command to run
- **Self-contained**: Include the full command, not just "see docs"
