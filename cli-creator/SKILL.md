---
name: cli-creator
description: >-
  Create CLI tools optimized for coding agents. Use this skill when the user
  asks to "create a CLI", "build a command-line tool", "wrap an API as a CLI",
  "make a CLI for coding agents", "build an agent-friendly CLI", or discusses
  building terminal tools, CLI wrappers for APIs/MCP servers, structured CLI
  output, or agent-readable command-line interfaces. Trigger this skill whenever
  CLIs, terminal tools, or command-line utilities are being built -- even if the
  user doesn't say "agent-friendly" -- because agent-first design makes better
  CLIs for everyone.
---

# CLI Creator -- Agent-First Command-Line Tools

A CLI built for coding agents is a better CLI for humans too. When output is
machine-parseable, errors are self-remediating, and every command is
discoverable without reading docs, both agents and humans move faster.

This skill guides you through creating CLI tools that follow the **Agent-First
Architecture** -- four principles drawn from real-world agent-optimized CLIs
like `ncli` (Notion CLI for coding agents).

---

## Phase 1 -- Understand the Use Case

Before writing code, gather these answers conversationally. Batch the questions
rather than asking one at a time:

1. **What does it wrap?** REST API, GraphQL, MCP server, gRPC, local
   filesystem, database, or pure computation?
2. **Who is the primary consumer?** Coding agents (Claude Code, Copilot, Cursor),
   human developers, or both? (Default: both)
3. **How many commands?** Rough count guides structure:
   - Under 10: flat command list
   - 10-30: subcommand groups
   - 30+: promote top 5-10 most-used commands, add `api` escape hatch for the rest
4. **What auth does the upstream need?** None, API key, OAuth 2.0, or other?
5. **Preferred language/framework?**

| Language | Recommended Framework | Reference |
|---|---|---|
| Node.js / TypeScript | Commander.js | `references/node-commander.md` |
| Python | Click or Typer | `references/python-click-typer.md` |
| Rust | Clap (derive) | `references/rust-clap.md` |
| Go | Cobra | `references/go-cobra.md` |

If the user has no preference, recommend **Node.js + Commander.js** for API
wrappers (rich ecosystem, easy JSON handling) or **Python + Typer** for
data/ML tools.

---

## Phase 2 -- Architecture

Every agent-friendly CLI follows a layered architecture that separates concerns
and maximizes testability:

```
CLI Framework (argument parsing, help, validation)
    ↓
buildXxxCall()  -- pure functions (CLI args → API params)
    ↓
withConnection()  -- lifecycle management (connect, retry, disconnect)
    ↓
API Client / SDK / MCP SDK
    ↓
Remote Service
```

### Why pure functions matter

The `buildXxxCall()` layer is the most important architectural decision. Each
command maps to one pure function that transforms CLI arguments into API call
parameters. No side effects, no I/O, no network calls.

```typescript
// Pure function -- easy to test without mocking
function buildSearchCall(query: string, opts: { limit?: number }) {
  return {
    tool: "search",
    args: { query, page_size: opts.limit ?? 20 }
  };
}
```

This means unit tests verify argument mapping without spinning up servers or
mocking HTTP clients. If every `buildXxxCall()` is correct, the CLI is correct
-- the remaining layers are thin glue.

### Connection lifecycle

Wrap API interactions in a single `withConnection(fn)` that handles:
- Connection setup and teardown
- Auth token injection
- Retry logic with exponential backoff
- Rate limit handling

Commands stay focused on their business logic because lifecycle concerns live
in one place.

---

## The Four Agent-First Principles

These four principles are the core of agent-friendly CLI design. Apply all of
them to every CLI you create.

### Principle 1: Agent-Readable Output

Agents parse output programmatically. Default to structured data, not prose.

- **Default mode**: JSON pretty-print with TTY detection. Colors and spinners
  in terminal, clean output in pipes.
- **`--json` flag**: Guarantees parseable JSON. If the upstream returns
  non-JSON, wrap it: `{ "text": "..." }`. Agents should always be able to
  rely on this flag.
- **`--raw` flag**: Unfiltered upstream response -- useful for debugging or
  when the CLI's formatting gets in the way.
- **Stdin support**: Accept piped input with `-` convention:
  `echo '{"body":"..."}' | mycli create --body -`

See `references/output-formatting.md` for implementation patterns per language.

### Principle 2: Built-in Discovery (Three-Layer Help)

Agents learn from errors and help text. Make every level discoverable:

1. **Root `--help`**: All commands + quick-start example
2. **Subcommand group `--help`**: Available sub-operations + common patterns
3. **Command `--help`**: All flags, usage examples, prerequisites, related
   commands

For agents, **error hints matter more than help text**. Agents rarely run
`--help` proactively -- they learn from what goes wrong. Invest in error
messages (see Principle 3).

### Principle 3: Structured Error Messages (What + Why + Hint)

Every error must answer three questions:

```
Error: Could not find page with ID "abc123"        ← What failed
Why:   The ID format is invalid -- expected UUID    ← Root cause
Hint:  Run `mycli search "page title"` to find      ← Concrete next step
       the correct page ID
```

When `--json` is active, errors are also structured:

```json
{
  "error": "Could not find page with ID \"abc123\"",
  "why": "The ID format is invalid -- expected UUID",
  "hint": "Run `mycli search \"page title\"` to find the correct page ID"
}
```

Implement a **hint rule system**: an array of `{ pattern, hint }` objects where
`pattern` is a regex matched against error messages. This makes hints
extensible -- add new rules as users report common errors.

See `references/error-handling.md` for the pattern-matching hint system.

### Principle 4: Escape Hatch

No CLI can wrap every API feature. Provide an `api` subcommand for direct,
unmediated access:

```bash
mycli api <endpoint-or-tool> '{"param": "value"}'
echo '{"param": "value"}' | mycli api <endpoint-or-tool>
```

This prevents feature lock-in. When an agent hits a wall with high-level
commands, it falls back to `api` without leaving the CLI.

---

## Phase 3 -- Command Design

### The "Search → Fetch → Act" Pattern

Most agent workflows follow three stages:

1. **Search**: Discover resources by name/query → returns IDs and summaries
2. **Fetch**: Retrieve full details by ID → returns complete data
3. **Act**: Mutate by ID → create, update, delete

Design commands around this workflow. Every mutation command should accept IDs
that search/fetch return. Never require an agent to "just know" an ID without
providing a discovery mechanism.

```bash
# Agent workflow example
mycli search "Q4 Sales Report" --json        # → returns page_id
mycli fetch abc-123-def --json               # → returns full page data
mycli update abc-123-def --title "Q4 Sales Report (Final)" --json
```

### Common Command Groups

| Group | Commands | Purpose |
|---|---|---|
| **Auth** | `login`, `logout`, `whoami` | Authentication setup |
| **Discovery** | `search`, `list` | Find resources, return IDs |
| **Retrieval** | `fetch`, `get`, `show` | Full details by ID |
| **CRUD** | `create`, `update`, `delete` | Mutations |
| **Escape hatch** | `api` | Direct API/tool invocation |

### Global Flags

Every command should support these flags:

| Flag | Purpose |
|---|---|
| `--json` | Guaranteed structured JSON output |
| `--raw` | Unfiltered upstream response |
| `--verbose` | Detailed logging to stderr |
| `--help` | Usage information |

---

## Phase 4 -- Scaffold and Implement

Read the reference file for the user's chosen language/framework. Each
reference contains:

- Project setup (package.json / pyproject.toml / Cargo.toml / go.mod)
- Recommended directory structure
- Scaffold code for CLI entry point, output layer, error layer, connection layer
- Framework-specific patterns for the four principles

| Language | Read this file |
|---|---|
| Node.js / TypeScript | `references/node-commander.md` |
| Python | `references/python-click-typer.md` |
| Rust | `references/rust-clap.md` |
| Go | `references/go-cobra.md` |

### Implementation Order

Follow this order to build incrementally -- each step is testable independently:

1. **Scaffold**: Project structure, dependencies, entry point
2. **Output layer**: `printOutput()` with TTY detection, `--json`, `--raw`
3. **Error layer**: Structured errors with hint system
4. **Connection layer**: `withConnection()` with retry logic
5. **First command**: Pick the simplest read command (e.g., `search` or
   `whoami`). Implement `buildSearchCall()` pure function + wire up.
6. **Auth** (if needed): OAuth/API-key flow. See `references/auth-patterns.md`
7. **Remaining commands**: One `buildXxxCall()` per command
8. **Escape hatch**: `api` subcommand
9. **Help text**: Polish three-layer help with examples and next-step hints

---

## Phase 5 -- Testing

The testing strategy mirrors the architecture -- test pure functions, not
network calls.

### Primary: Unit tests for `buildXxxCall()` pure functions

Each test verifies that CLI arguments map to the correct API parameters. No
mocking required.

```typescript
test("buildSearchCall sets default page_size", () => {
  const call = buildSearchCall("my query", {});
  expect(call.args.page_size).toBe(20);
});

test("buildSearchCall respects limit option", () => {
  const call = buildSearchCall("my query", { limit: 5 });
  expect(call.args.page_size).toBe(5);
});
```

### Secondary: Output formatting and error hint tests

- Verify `--json` mode wraps output correctly
- Verify `--raw` mode passes through unmodified
- Verify error hint patterns match expected messages

### Optional: Integration tests

For complex CLIs, spin up a mock server and run commands end-to-end.

See `references/testing-strategies.md` for framework-specific test setup.

---

## Phase 6 -- Polish and Ship

1. **README**: Installation, quick-start, command reference
2. **Tab completion**: Most frameworks support shell completion generation
3. **npm/pip/cargo publish**: Package for distribution
4. **CLAUDE.md**: If the CLI is meant to be used by Claude Code in a project,
   add a CLAUDE.md with common workflows

---

## Reference Files

Read these as needed during implementation:

| File | When to read |
|---|---|
| `references/node-commander.md` | Building with Node.js / TypeScript |
| `references/python-click-typer.md` | Building with Python |
| `references/rust-clap.md` | Building with Rust |
| `references/go-cobra.md` | Building with Go |
| `references/output-formatting.md` | Implementing output modes |
| `references/error-handling.md` | Implementing error hints |
| `references/auth-patterns.md` | Adding authentication |
| `references/testing-strategies.md` | Setting up tests |

## Example Files

Working code examples in `examples/`:

- `examples/node-search-cli/` -- Node.js/TypeScript: build-calls, output,
  errors, and tests
- `examples/python-crud-cli/` -- Python: build_calls, output, errors, and tests
