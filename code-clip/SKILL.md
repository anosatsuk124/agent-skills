---
name: code-clip
description: >-
  Manage code snippets across files using named clipboards. Use this skill
  when the user asks to "copy this code", "move this function", "save this
  snippet", "paste that code here", "compare these code blocks", or wants to
  transfer code between files, cut and move blocks, track refactoring
  operations, or manage intermediate code states during complex multi-step
  edits. Also trigger when the user mentions "clipboard", "snippet",
  "code clip", "save for later", "remember this code", "stack", or needs to
  collect scattered fragments to merge them. Trigger any time a coding agent
  would benefit from a temporary, named holding area for code.
argument-hint: "[command] [name]"
allowed-tools:
  - Bash(uv:*)
  - Read
  - Write
  - Edit
  - Bash(cat:*)
  - Bash(wc:*)
---

# Code Clip — Named Clipboard Manager for Code Snippets

`code-clip` is a file-backed, multi-clipboard CLI for storing, retrieving,
searching, and comparing code fragments. It lives in a `.code-clip/` directory
in the current working directory.

It is a **uv project** located at `<agent-skills-root>/code-clip/cli/`. Run all
commands via `uv run --directory <path-to-cli> code-clip ...`.

Always use `--json` when consuming output programmatically. Raw content is
available via `--raw`.

---

## Prerequisites

### Step 1: Locate the CLI directory

Find the absolute path to the CLI:

```bash
# Typically within the agent-skills repo
CODE_CLIP_CLI="$(dirname "$(find ~ -path '*/agent-skills/code-clip/cli/pyproject.toml' 2>/dev/null | head -1)")"
echo "$CODE_CLIP_CLI"
```

### Step 2: Verify uv is available

```bash
uv --version
```

If not found, install via mise: `mise use -g uv`

### Step 3: Verify code-clip works

```bash
uv run --directory "$CODE_CLIP_CLI" code-clip --help
```

If dependencies are missing, run `uv sync --dev` in the CLI directory first.

Set a shell variable for convenience in the rest of the session:

```bash
CLIP="uv run --directory $CODE_CLIP_CLI code-clip"
```

Then use `$CLIP <command>` throughout the workflow.

---

## Core Workflows

### Workflow A: Copy and Paste (code duplication)

Use when replicating a function or block to another file.

```bash
# 1. Copy from source file (lines 15-30)
$CLIP copy auth-func --file src/auth.py --lines 15-30 --tag refactor --json

# 2. Read the content to paste
$CLIP paste auth-func --json
# → {"name": "auth-func", "content": "..."}

# 3. Write the content into the destination file with Edit or Write

# 4. Clean up
$CLIP delete auth-func --force
```

**Key: `$CLIP paste --json` returns structured output; extract `.content` to insert.**

---

### Workflow B: Cut and Move (code relocation)

`cut` saves content AND records which file/lines to remove. The CLI never
modifies source files — you perform the deletion with Edit.

```bash
# 1. Cut the function (records removal intent)
$CLIP cut helper-func --file src/utils.py --lines 40-55 --json
# → {"name": "helper-func", "operation": "cut",
#    "removal_descriptor": {"file": "/abs/path/src/utils.py",
#                           "line_start": 40, "line_end": 55, ...}}

# 2. Remove the original lines from src/utils.py using Edit
#    (use the removal_descriptor.line_start and line_end values)

# 3. Paste into the destination
$CLIP paste helper-func --json

# 4. Write the content into the new file

# 5. Clean up
$CLIP delete helper-func --force
```

**The `removal_descriptor` in the cut result tells you exactly what to delete.**

---

### Workflow C: Stack-based Sequential Refactor

When moving multiple pieces in sequence, use the stack so you don't lose
ordering.

```bash
# Save multiple pieces (LIFO: last-in, first-out)
$CLIP copy step1 --file a.py --lines 10-20 --push --json
$CLIP copy step2 --file b.py --lines 5-15 --push --json

# Work on the refactor...

# Retrieve in reverse order (step2 first, then step1)
$CLIP stack pop --json   # → step2 content
$CLIP stack pop --json   # → step1 content
```

Or use `stack push` to push existing clipboard entries:

```bash
$CLIP copy snippet-a --file x.py --json
$CLIP stack push snippet-a --json
```

---

### Workflow D: Compare Before / After

```bash
# Snapshot current state
$CLIP copy before --file src/payment.py --tag checkpoint --json

# Make your changes...

# Snapshot new state
$CLIP copy after --file src/payment.py --tag checkpoint --json

# Compare
$CLIP diff before after --json
# → {"diff": "--- before\n+++ after\n...", "changed": true}

# Clean up
$CLIP clear --tag checkpoint --force
```

---

### Workflow E: Collect Scattered Fragments and Merge

```bash
# Collect from multiple sources
$CLIP copy part1 --file a.py --lines 1-10 --tag merge --json
$CLIP copy part2 --file b.py --lines 20-30 --tag merge --json

# Merge into one
$CLIP merge combined part1 part2 --separator "\n\n" --json

# Use the combined result
$CLIP paste combined --json

# Clean up all at once
$CLIP clear --tag merge --force
```

---

### Workflow F: Verify Source Hasn't Changed

During a long refactor, verify a saved snippet still matches its source:

```bash
$CLIP verify auth-func --json
# → {"verified": true}  or  {"verified": false, "reason": "Source changed"}
```

If `verified` is `false`, re-read the source before pasting.

---

## Command Reference

| Command | Purpose | Key Flags |
|---|---|---|
| `copy <name>` | Store content | `--file`, `--lines`, `--lang`, `--tag`, `--overwrite`, `--push` |
| `cut <name>` | Store + record removal intent | same + `--dry-run` |
| `paste <name>` | Retrieve content | `--pop`, `--strip-indent`, `--indent` |
| `list` | Show all entries | `--tag`, `--lang`, `--sort`, `--limit` |
| `show <name>` | Full details + metadata | — |
| `delete <name>` | Remove entry | `--force` |
| `clear` | Remove all (or by tag) | `--tag`, `--force` |
| `search <query>` | Find by name/content/tag | `--in`, `--lang`, `--limit` |
| `diff <n1> <n2>` | Unified diff | `--context` |
| `verify <name>` | Check source integrity | — |
| `merge <target> <s1>...` | Combine entries | `--separator`, `--delete-sources` |
| `stack push <name>` | Push onto LIFO stack | — |
| `stack pop` | Pop from LIFO stack | `--peek`, `--name` |
| `stack list` | Show stack | — |
| `export` | Serialize all to JSON | `--output` |
| `import <file>` | Restore from JSON | `--overwrite` |

**Always add `--json` when consuming output in code.**

---

## Best Practices for Agents

1. **Set `$CLIP` at the start** — avoids repeating the `--directory` path every call.
2. **Use `--json` for all programmatic reads** — structured output is reliable.
3. **Name entries meaningfully** — `auth-validate-func` beats `clip1`.
4. **Tag by intent** — `--tag refactor`, `--tag move`, `--tag checkpoint`.
5. **Use `cut` for move operations** — the `removal_descriptor` tells you what to delete.
6. **Use the stack for ordered multi-step operations** — LIFO ordering is automatic.
7. **Verify before pasting in long sessions** — `$CLIP verify <name> --json`.
8. **Clean up after completing workflows** — `$CLIP clear --tag <tag> --force`.

---

## Error Recovery

| Error | Cause | Fix |
|---|---|---|
| `Clipboard '<name>' not found` | Wrong name or already deleted | `$CLIP list --json` to check |
| `Clipboard '<name>' already exists` | Duplicate name | Use `--overwrite` or different name |
| `Stack is empty` | Nothing pushed | Use `--push` on copy or `stack push` |
| `Content is empty` | Empty stdin or file | Check file path or pipe content |
| `Invalid line range` | Bad `--lines` format | Use `N` or `N-M`, e.g. `10-25` |
| `uv: command not found` | uv not in PATH | Run `mise use -g uv` or add to PATH |
