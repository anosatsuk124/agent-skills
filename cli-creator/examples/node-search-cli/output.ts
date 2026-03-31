/**
 * Output layer: handles --json, --raw, and default TTY-aware formatting.
 */

export interface OutputOptions {
  json?: boolean;
  raw?: boolean;
}

/**
 * Print data to stdout in the appropriate format.
 *
 * - --raw: pass through exactly as received
 * - --json: guaranteed parseable JSON (wraps strings in { text: "..." })
 * - default: JSON pretty-print in TTY, clean JSON in pipes
 */
export function printOutput(data: unknown, opts: OutputOptions = {}): void {
  if (opts.raw) {
    process.stdout.write(
      typeof data === "string" ? data : JSON.stringify(data)
    );
    return;
  }

  if (opts.json || !process.stdout.isTTY) {
    const output =
      typeof data === "string"
        ? JSON.stringify({ text: data }, null, 2)
        : JSON.stringify(data, null, 2);
    console.log(output);
    return;
  }

  // Human-friendly TTY output
  printPretty(data);
}

/**
 * Print human-friendly output to the terminal.
 */
function printPretty(data: unknown): void {
  if (Array.isArray(data)) {
    printTable(data);
  } else if (typeof data === "object" && data !== null) {
    printKeyValue(data as Record<string, unknown>);
  } else {
    console.log(data);
  }
}

/**
 * Print an array of objects as a simple table.
 */
function printTable(rows: unknown[]): void {
  if (rows.length === 0) {
    console.log("(no results)");
    return;
  }

  const first = rows[0];
  if (typeof first !== "object" || first === null) {
    rows.forEach((row) => console.log(row));
    return;
  }

  const keys = Object.keys(first);
  const widths = keys.map((k) =>
    Math.max(
      k.length,
      ...rows.map((r) => String((r as Record<string, unknown>)[k] ?? "").length)
    )
  );

  // Header
  console.log(keys.map((k, i) => k.padEnd(widths[i])).join("  "));
  console.log(widths.map((w) => "─".repeat(w)).join("  "));

  // Rows
  for (const row of rows) {
    const r = row as Record<string, unknown>;
    console.log(keys.map((k, i) => String(r[k] ?? "").padEnd(widths[i])).join("  "));
  }
}

/**
 * Print an object as key-value pairs.
 */
function printKeyValue(obj: Record<string, unknown>): void {
  const maxKeyLen = Math.max(...Object.keys(obj).map((k) => k.length));
  for (const [key, value] of Object.entries(obj)) {
    const displayValue =
      typeof value === "object" ? JSON.stringify(value) : String(value);
    console.log(`${key.padEnd(maxKeyLen)}  ${displayValue}`);
  }
}
