/**
 * Structured error handling with the pattern-matching hint system.
 * Errors follow the "What + Why + Hint" format.
 */

import type { OutputOptions } from "./output";

// --- Structured Error ---

export class StructuredError extends Error {
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

// --- Hint Rules ---

interface HintRule {
  /** Regex pattern to match against the error message */
  pattern: RegExp;
  /** Optional: only apply to errors from specific commands */
  command?: string;
  /** The hint to show when the pattern matches */
  hint: string;
}

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
    hint: "Check that your account has access. Run `mycli whoami` to verify.",
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
    hint: "A resource with this name already exists. Use `mycli update` to modify it.",
  },
  {
    pattern: /validation|invalid.*param|missing.*required/i,
    hint: "Check required parameters with `mycli <command> --help`.",
  },
];

// --- Hint Matching ---

export function findHint(error: Error, command?: string): string | undefined {
  const message = error.message;
  for (const rule of HINT_RULES) {
    if (rule.command && rule.command !== command) continue;
    if (rule.pattern.test(message)) return rule.hint;
  }
  return undefined;
}

export function enrichError(error: Error, command?: string): StructuredError {
  if (error instanceof StructuredError) return error;
  const hint = findHint(error, command);
  return new StructuredError(error.message, { hint });
}

// --- Error Output ---

export function printError(err: StructuredError, opts: OutputOptions = {}): void {
  if (opts.json) {
    console.error(JSON.stringify(err.toJSON(), null, 2));
  } else {
    console.error(`Error: ${err.message}`);
    if (err.why) console.error(`Why:   ${err.why}`);
    if (err.hint) console.error(`Hint:  ${err.hint}`);
  }
  process.exitCode = 1;
}
