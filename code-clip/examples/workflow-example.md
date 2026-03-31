# code-clip Workflow Examples

Real-world examples showing how a coding agent uses `code-clip` during
multi-file refactoring tasks.

All examples assume `$CLIP` is set:

```bash
CODE_CLIP_CLI="$(dirname "$(find ~ -path '*/agent-skills/code-clip/cli/pyproject.toml' 2>/dev/null | head -1)")"
CLIP="uv run --directory $CODE_CLIP_CLI code-clip"
```

---

## Example 1: Move a Function to a New Module

**Goal:** Move `validate_email()` from `src/utils.py` (lines 42-60) to `src/validators.py`.

```bash
# Step 1: Cut the function (record removal intent, save content)
$ $CLIP cut email-validator --file src/utils.py --lines 42-60 --lang python --tag move --json
{
  "name": "email-validator",
  "operation": "cut",
  "removal_descriptor": {
    "action": "delete_lines",
    "file": "/project/src/utils.py",
    "line_start": 42,
    "line_end": 60,
    "note": "Remove these lines from the source file using your editor."
  }
}

# Step 2: Agent uses Edit to remove lines 42-60 from src/utils.py

# Step 3: Retrieve content for the destination
$ $CLIP paste email-validator --json
{
  "name": "email-validator",
  "content": "def validate_email(email: str) -> bool:\n    ...\n"
}

# Step 4: Agent writes content into src/validators.py using Write or Edit

# Step 5: Clean up
$ $CLIP delete email-validator --force
```

---

## Example 2: Multi-Step Refactor with Stack

**Goal:** Extract 3 methods from a class into standalone functions, preserving order.

```bash
# Step 1: Copy each method, pushing onto the stack
$ $CLIP copy parse-method --file src/parser.py --lines 10-25 --push --json
$ $CLIP copy validate-method --file src/parser.py --lines 30-45 --push --json
$ $CLIP copy format-method --file src/parser.py --lines 50-65 --push --json

# stack is: [format-method, validate-method, parse-method] (LIFO)

# Step 2: Retrieve in extraction order (last pushed = first popped)
$ $CLIP stack pop --json  # → format-method
$ $CLIP stack pop --json  # → validate-method
$ $CLIP stack pop --json  # → parse-method

# Step 3: For each, write into the new functions.py file
```

---

## Example 3: Before/After Comparison

**Goal:** Refactor `calculate_total()` and verify what changed.

```bash
# Step 1: Snapshot before
$ $CLIP copy total-before --file src/billing.py --lines 100-130 --tag checkpoint --json

# Step 2: Refactor the function...

# Step 3: Snapshot after
$ $CLIP copy total-after --file src/billing.py --lines 100-130 --tag checkpoint --json

# Step 4: Compare
$ $CLIP diff total-before total-after --json
{
  "name1": "total-before",
  "name2": "total-after",
  "diff": "--- total-before\n+++ total-after\n@@ -5,7 +5,4 @@\n ...",
  "changed": true
}

# Step 5: Clean up checkpoints
$ $CLIP clear --tag checkpoint --force
```

---

## Example 4: Collect and Merge Related Constants

**Goal:** Gather error constants from 3 files into one `constants.py`.

```bash
# Collect
$ $CLIP copy http-errors --file src/http.py --lines 1-20 --tag collect --json
$ $CLIP copy db-errors --file src/database.py --lines 5-15 --tag collect --json
$ $CLIP copy auth-errors --file src/auth.py --lines 1-10 --tag collect --json

# Merge with a blank line separator
$ $CLIP merge all-errors http-errors db-errors auth-errors \
    --separator "\n\n" --delete-sources --json
{
  "target": "all-errors",
  "sources": ["http-errors", "db-errors", "auth-errors"]
}

# Write into constants.py
$ $CLIP paste all-errors --raw > src/constants.py

# Final cleanup
$ $CLIP delete all-errors --force
```

---

## Example 5: Verify Source Integrity Before Paste

**Goal:** In a long session, make sure a saved snippet still matches the source.

```bash
# Earlier in the session, you saved a snippet
$ $CLIP copy payment-logic --file src/payment.py --lines 50-80 --json

# ... many edits later ...

# Before pasting, verify the source hasn't shifted
$ $CLIP verify payment-logic --json
{
  "name": "payment-logic",
  "verified": false,
  "reason": "Source content has changed since snippet was captured.",
  "stored_checksum": "sha256:abc...",
  "current_checksum": "sha256:xyz..."
}

# Source changed — re-copy before pasting
$ $CLIP copy payment-logic --file src/payment.py --lines 50-80 --overwrite --json
```

---

## Example 6: Export and Resume in a New Session

**Goal:** Save clipboard state at end of session, restore in the next one.

```bash
# End of session: export all
$ $CLIP export --output .code-clip-session.json --json
{
  "exported_to": ".code-clip-session.json",
  "count": 4
}

# Next session: import
$ $CLIP import .code-clip-session.json --json
{
  "imported": ["auth-func", "helper", "payment-logic", "test-util"],
  "skipped": []
}
```

---

## Output Format Reference

### `--json` (structured, always parseable)
```json
{
  "name": "my-snippet",
  "content": "def foo():\n    pass\n",
  "metadata": {
    "language": "python",
    "operation": "copy",
    "tags": ["refactor"],
    "source_file": "/project/src/utils.py",
    "line_start": 10,
    "line_end": 15,
    "created_at": "2026-03-31T09:00:00+00:00",
    "checksum": "sha256:abc..."
  }
}
```

### `--raw` (content only, for direct insertion)
```
def foo():
    pass
```

### Default TTY output (human-readable table for `list`)
```
Clipboards (3 entries)
------------------------------------------------------------
  my-snippet    python       [CUT]      12 lines  [refactor]
  auth-func     python               8 lines  [security]
  config-blob   yaml                 25 lines
```

---

## Running Tests

```bash
uv run --directory "$CODE_CLIP_CLI" pytest tests/ -v
```
