# Node.js / TypeScript + Commander.js Reference

Implements the Agent-First Architecture from SKILL.md using Commander.js.

---

## Project Setup

```json
// package.json
{
  "name": "mycli",
  "version": "0.1.0",
  "type": "module",
  "bin": { "mycli": "./dist/cli.js" },
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch",
    "test": "vitest run",
    "prepublishOnly": "npm run build"
  },
  "files": ["dist"],
  "dependencies": { "commander": "^13.0.0", "env-paths": "^3.0.0" },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "typescript": "^5.7.0",
    "vitest": "^3.0.0"
  }
}
```

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022", "module": "Node16", "moduleResolution": "Node16",
    "outDir": "dist", "rootDir": "src", "strict": true,
    "esModuleInterop": true, "declaration": true, "sourceMap": true
  },
  "include": ["src"]
}
```

## Directory Structure

```
src/
├── cli.ts          Commander program definition + entry point
├── commands/       One file per command group
├── build-calls/    Pure functions: CLI args → API params
├── connection.ts   withConnection wrapper
├── output.ts       printOutput with TTY detection
├── errors.ts       Structured errors + hint rules
└── auth.ts         Optional: OAuth / API key
```

---

## CLI Entry Point -- `src/cli.ts`

```typescript
#!/usr/bin/env node
import { Command } from "commander";
import { registerSearchCommand } from "./commands/search.js";
import { registerApiCommand } from "./commands/api.js";
import { formatError } from "./errors.js";

export interface GlobalOpts { json?: boolean; raw?: boolean; verbose?: boolean }

export function getGlobalOpts(cmd: Command): GlobalOpts {
  let root = cmd;
  while (root.parent) root = root.parent;
  return root.opts() as GlobalOpts;
}

const program = new Command();
program
  .name("mycli")
  .description("Agent-friendly CLI for MyService")
  .version("0.1.0")
  .option("--json", "Output as structured JSON")
  .option("--raw", "Output unfiltered upstream response")
  .option("--verbose", "Detailed logging to stderr");

registerSearchCommand(program);
registerApiCommand(program);
// register additional commands here

program.exitOverride();

async function main() {
  try {
    await program.parseAsync(process.argv);
  } catch (err: unknown) {
    process.stderr.write(formatError(err, program.opts()) + "\n");
    process.exit(1);
  }
}
main();
```

---

## Output Layer -- `src/output.ts`

```typescript
import type { GlobalOpts } from "./cli.js";

export function printOutput(data: unknown, opts: GlobalOpts & { rawText?: string }): void {
  if (opts.rawText) {                         // --raw passthrough
    process.stdout.write(opts.rawText + "\n");
    return;
  }
  if (opts.json) {                            // --json guaranteed JSON
    const obj = typeof data === "string" ? { text: data } : data;
    process.stdout.write(JSON.stringify(obj) + "\n");
    return;
  }
  if (typeof data === "string") {             // default: strip ANSI in pipes
    const out = process.stdout.isTTY ? data : data.replace(/\x1B\[[0-9;]*[A-Za-z]/g, "");
    process.stdout.write(out + "\n");
  } else {                                    // default: pretty in TTY, compact in pipe
    process.stdout.write(JSON.stringify(data, null, process.stdout.isTTY ? 2 : 0) + "\n");
  }
}

export function verbose(msg: string, opts: GlobalOpts): void {
  if (opts.verbose) process.stderr.write(`[verbose] ${msg}\n`);
}
```

---

## Error Layer -- `src/errors.ts`

```typescript
export class StructuredError extends Error {
  constructor(message: string, public why?: string, public hint?: string) {
    super(message);
    this.name = "StructuredError";
  }
}

export interface HintRule { pattern: RegExp; hint: string }

export const defaultHintRules: HintRule[] = [
  { pattern: /not[_ ]found|404|does not exist/i,
    hint: 'Run `mycli search "<name>"` to find the correct ID.' },
  { pattern: /unauthorized|401|invalid.*token/i,
    hint: "Run `mycli login` or check your API key." },
  { pattern: /forbidden|403|permission/i,
    hint: "You lack permission for this resource." },
  { pattern: /rate[_ ]limit|429|too many requests/i,
    hint: "Rate limited -- wait a moment and retry." },
  { pattern: /timeout|ETIMEDOUT|ECONNRESET/i,
    hint: "Request timed out. Check your connection and retry." },
];

export function applyHintRules(msg: string, rules = defaultHintRules): string | undefined {
  return rules.find((r) => r.pattern.test(msg))?.hint;
}

export function formatError(err: unknown, opts: { json?: boolean } = {}): string {
  const se = err instanceof StructuredError
    ? err
    : new StructuredError(
        err instanceof Error ? err.message : String(err),
        undefined,
        applyHintRules(err instanceof Error ? err.message : String(err))
      );

  if (opts.json) {
    const obj: Record<string, string> = { error: se.message };
    if (se.why) obj.why = se.why;
    if (se.hint) obj.hint = se.hint;
    return JSON.stringify(obj);
  }

  let out = `Error: ${se.message}`;
  if (se.why) out += `\nWhy:   ${se.why}`;
  if (se.hint) out += `\nHint:  ${se.hint}`;
  return out;
}
```

---

## Connection Layer -- `src/connection.ts`

```typescript
import { verbose } from "./output.js";
import { StructuredError } from "./errors.js";
import type { GlobalOpts } from "./cli.js";

export interface ConnectionContext {
  baseUrl: string;
  token: string;
  opts: GlobalOpts;
}

export async function withConnection<T>(
  opts: GlobalOpts,
  fn: (ctx: ConnectionContext) => Promise<T>
): Promise<T> {
  const token = process.env.MYCLI_TOKEN;
  if (!token) {
    throw new StructuredError(
      "No authentication token found",
      "MYCLI_TOKEN environment variable is not set.",
      "Run `mycli login` or export MYCLI_TOKEN."
    );
  }
  const baseUrl = process.env.MYCLI_BASE_URL ?? "https://api.myservice.com";
  const ctx: ConnectionContext = { baseUrl, token, opts };
  verbose(`Connecting to ${baseUrl}`, opts);

  const maxRetries = 3;
  let lastErr: unknown;
  for (let i = 1; i <= maxRetries; i++) {
    try {
      return await fn(ctx);
    } catch (err: unknown) {
      lastErr = err;
      const msg = err instanceof Error ? err.message : String(err);
      if (!/rate.limit|429|timeout|ETIMEDOUT|ECONNRESET|503|502/i.test(msg)) throw err;
      if (i < maxRetries) {
        const delay = Math.min(1000 * 2 ** (i - 1), 8000);
        verbose(`Attempt ${i} failed. Retrying in ${delay}ms...`, opts);
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }
  throw new StructuredError(
    `Failed after ${maxRetries} attempts`,
    lastErr instanceof Error ? lastErr.message : String(lastErr),
    "Check your network connection and try again."
  );
}
```

---

## Command Implementation Pattern

Every command wires three layers: **buildXxxCall** (pure) ->
**withConnection** (lifecycle) -> **printOutput** (formatting).

### Pure function -- `src/build-calls/search.ts`

```typescript
export interface SearchCallParams {
  endpoint: string;
  method: "POST";
  body: { query: string; page_size: number; filter?: Record<string, unknown> };
}

export function buildSearchCall(
  query: string,
  opts: { limit?: number; filter?: string }
): SearchCallParams {
  return {
    endpoint: "/v1/search",
    method: "POST",
    body: {
      query,
      page_size: opts.limit ?? 20,
      ...(opts.filter && { filter: JSON.parse(opts.filter) }),
    },
  };
}
```

### Command registration -- `src/commands/search.ts`

```typescript
import type { Command } from "commander";
import { buildSearchCall } from "../build-calls/search.js";
import { withConnection } from "../connection.js";
import { printOutput, verbose } from "../output.js";
import { getGlobalOpts } from "../cli.js";

export function registerSearchCommand(program: Command): void {
  program
    .command("search <query>")
    .description("Search resources by name or keyword")
    .option("-l, --limit <n>", "Max results", "20")
    .option("--filter <json>", "JSON filter object")
    .action(async (query: string, localOpts, cmd: Command) => {
      const gOpts = getGlobalOpts(cmd);
      const call = buildSearchCall(query, {
        limit: parseInt(localOpts.limit, 10),
        filter: localOpts.filter,
      });
      verbose(`Call: ${JSON.stringify(call)}`, gOpts);

      const result = await withConnection(gOpts, async (ctx) => {
        const res = await fetch(`${ctx.baseUrl}${call.endpoint}`, {
          method: call.method,
          headers: { Authorization: `Bearer ${ctx.token}`, "Content-Type": "application/json" },
          body: JSON.stringify(call.body),
        });
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${await res.text()}`);
        return res.json();
      });

      printOutput(result, gOpts);
    });
}
```

### Unit test -- `src/build-calls/search.test.ts`

```typescript
import { describe, it, expect } from "vitest";
import { buildSearchCall } from "./search.js";

describe("buildSearchCall", () => {
  it("defaults page_size to 20", () => {
    expect(buildSearchCall("q", {}).body.page_size).toBe(20);
  });
  it("respects limit", () => {
    expect(buildSearchCall("q", { limit: 5 }).body.page_size).toBe(5);
  });
  it("parses filter JSON", () => {
    expect(buildSearchCall("q", { filter: '{"status":"active"}' }).body.filter)
      .toEqual({ status: "active" });
  });
  it("omits filter when absent", () => {
    expect(buildSearchCall("q", {}).body.filter).toBeUndefined();
  });
});
```

---

## Package and Distribution

**Shebang**: First line of `src/cli.ts` must be `#!/usr/bin/env node`.
TypeScript preserves this in the compiled output.

**Build and link locally**:

```bash
npm run build && chmod +x dist/cli.js
npm link        # symlinks 'mycli' into PATH
mycli --help
```

**Global install**: `npm install -g mycli`

**Config paths** -- use `env-paths` for cross-platform directories:

```typescript
import envPaths from "env-paths";
const paths = envPaths("mycli", { suffix: "" });
// paths.config  ~/.config/mycli (Linux) | ~/Library/Preferences/mycli (macOS)
// paths.cache   ~/.cache/mycli
```

Store auth tokens in `paths.config`, cached data in `paths.cache`.
