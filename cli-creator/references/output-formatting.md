# Output Formatting Patterns

Cross-language guide for implementing the three output modes in agent-friendly
CLIs. Read this when implementing the output layer.

---

## The Three Output Modes

| Mode | Flag | Behavior |
|---|---|---|
| **Default** | (none) | Smart formatting: JSON pretty-print in terminal, clean JSON in pipes |
| **JSON** | `--json` | Guaranteed parseable JSON. Non-JSON responses wrapped in `{ "text": "..." }` |
| **Raw** | `--raw` | Upstream response passed through unmodified |

### Mode Selection Logic

```
if --raw flag:
    print upstream response as-is
elif --json flag:
    print JSON (wrap non-JSON in { "text": "..." })
elif stdout is TTY:
    print human-friendly (colors, tables, truncation)
else:
    print clean JSON (no colors, no spinners)
```

The key insight: **default mode detects whether output goes to a terminal or a
pipe**. In a terminal, humans get colors and formatting. In a pipe (or when an
agent captures output), they get clean JSON. The `--json` flag is an explicit
override that guarantees JSON regardless of context.

---

## TTY Detection by Language

### Node.js / TypeScript

```typescript
const isTTY = process.stdout.isTTY ?? false;
```

### Python

```python
import sys
is_tty = sys.stdout.isatty()
```

### Rust

```rust
use std::io::IsTerminal;
let is_tty = std::io::stdout().is_terminal();
```

### Go

```go
import "github.com/mattn/go-isatty"
import "os"
isTTY := isatty.IsTerminal(os.Stdout.Fd())
```

---

## Implementation Pattern

### Core `printOutput` Function

The output function takes three inputs:
1. The data to print (from the API response)
2. Output mode flags (json, raw)
3. Whether stdout is a TTY (auto-detected)

```typescript
// TypeScript example
interface OutputOptions {
  json?: boolean;
  raw?: boolean;
}

function printOutput(data: unknown, opts: OutputOptions): void {
  if (opts.raw) {
    // Pass through exactly as received
    process.stdout.write(
      typeof data === "string" ? data : JSON.stringify(data)
    );
    return;
  }

  if (opts.json || !process.stdout.isTTY) {
    // Guaranteed JSON -- wrap strings if needed
    const output = typeof data === "string"
      ? JSON.stringify({ text: data }, null, 2)
      : JSON.stringify(data, null, 2);
    console.log(output);
    return;
  }

  // Human-friendly TTY output
  printPretty(data);
}
```

```python
# Python example
import json
import sys

def print_output(data: Any, *, json_mode: bool = False, raw: bool = False) -> None:
    if raw:
        print(data if isinstance(data, str) else json.dumps(data))
        return

    if json_mode or not sys.stdout.isatty():
        output = (
            json.dumps({"text": data}, indent=2)
            if isinstance(data, str)
            else json.dumps(data, indent=2)
        )
        print(output)
        return

    # Human-friendly TTY output
    print_pretty(data)
```

---

## JSON Wrapping Rules

When `--json` is active, the output **must** be valid JSON. Follow these rules:

| Upstream response | Output |
|---|---|
| JSON object | Pass through as-is |
| JSON array | Pass through as-is |
| Plain text string | Wrap: `{ "text": "the string" }` |
| Binary / non-text | Wrap: `{ "error": "Binary response", "size_bytes": 1234 }` |
| Empty response | Output: `{ "ok": true }` |

---

## Stdin Support

Accept piped input with the `-` convention:

```bash
# Read body from stdin
echo '{"title": "New Page"}' | mycli create --body -

# Pipe file content
cat data.json | mycli import --data -
```

Implementation:

```typescript
function readStdin(): Promise<string> {
  return new Promise((resolve) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
  });
}

// In command handler
const body = opts.body === "-" ? await readStdin() : opts.body;
```

```python
import sys

def read_stdin() -> str:
    if not sys.stdin.isatty():
        return sys.stdin.read()
    return ""

# In command handler
body = read_stdin() if opts.body == "-" else opts.body
```

---

## Human-Friendly Formatting (TTY Mode)

When outputting to a terminal, enhance readability:

### Tables for list data

```typescript
// Use a simple table formatter for arrays of objects
function printPretty(data: unknown): void {
  if (Array.isArray(data)) {
    // Print as table with columns derived from object keys
    printTable(data);
  } else if (typeof data === "object" && data !== null) {
    // Print key-value pairs
    printKeyValue(data as Record<string, unknown>);
  } else {
    console.log(data);
  }
}
```

### Truncation for long values

In TTY mode, truncate long strings to terminal width. Show full data only in
`--json` or `--raw` mode.

### Colors

Use colors sparingly -- highlight IDs, status values, and errors. Always
check TTY before emitting color codes. Libraries:

- Node.js: `chalk` (auto-detects TTY)
- Python: `rich` or `click.style()`
- Rust: `colored` crate
- Go: `fatih/color`

---

## Error Output

Errors go to **stderr**, not stdout. This keeps stdout clean for piping:

```typescript
function printError(err: StructuredError, opts: OutputOptions): void {
  if (opts.json) {
    // Structured JSON error to stderr
    console.error(JSON.stringify({
      error: err.message,
      why: err.why,
      hint: err.hint,
    }, null, 2));
  } else {
    console.error(`Error: ${err.message}`);
    if (err.why) console.error(`Why:   ${err.why}`);
    if (err.hint) console.error(`Hint:  ${err.hint}`);
  }
  process.exitCode = 1;
}
```

Set a non-zero exit code so agents can detect failure programmatically.
