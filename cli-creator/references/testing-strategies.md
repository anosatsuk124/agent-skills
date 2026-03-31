# Testing Strategies

How to test agent-friendly CLIs effectively. The core principle: test pure
functions, not network calls.

---

## Testing Philosophy

The layered architecture (buildXxxCall → withConnection → API) means most
testing happens at the `buildXxxCall` layer. These are pure functions with no
I/O, no mocking required, and fast execution.

| Layer | Test Type | Priority |
|---|---|---|
| `buildXxxCall()` pure functions | Unit tests | **Primary** |
| Output formatting | Unit tests | Secondary |
| Error hint matching | Unit tests | Secondary |
| End-to-end commands | Integration tests | Optional |

---

## Unit Testing `buildXxxCall()` Functions

Each test verifies that CLI arguments produce the correct API parameters.

### Node.js / TypeScript (vitest)

```typescript
// build-calls.test.ts
import { describe, test, expect } from "vitest";
import { buildSearchCall, buildCreateCall, buildUpdateCall } from "./build-calls";

describe("buildSearchCall", () => {
  test("sets default page_size when no limit provided", () => {
    const call = buildSearchCall("my query", {});
    expect(call).toEqual({
      tool: "search",
      args: { query: "my query", page_size: 20 },
    });
  });

  test("respects custom limit", () => {
    const call = buildSearchCall("my query", { limit: 5 });
    expect(call.args.page_size).toBe(5);
  });

  test("passes filter when provided", () => {
    const call = buildSearchCall("query", { filter: "database" });
    expect(call.args.filter).toEqual({ property: "object", value: "database" });
  });
});

describe("buildCreateCall", () => {
  test("constructs create call with required fields", () => {
    const call = buildCreateCall({
      parent: "page-id-123",
      title: "New Page",
    });
    expect(call.tool).toBe("create_page");
    expect(call.args.parent_id).toBe("page-id-123");
    expect(call.args.properties.title).toBe("New Page");
  });

  test("includes optional body when provided", () => {
    const call = buildCreateCall({
      parent: "page-id-123",
      title: "New Page",
      body: "Some content",
    });
    expect(call.args.children).toBeDefined();
  });
});
```

**Setup** (`package.json`):
```json
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "devDependencies": {
    "vitest": "^3.0.0"
  }
}
```

### Python (pytest)

```python
# test_build_calls.py
from build_calls import build_search_call, build_create_call, build_update_call

def test_search_default_page_size():
    call = build_search_call("my query")
    assert call == {
        "tool": "search",
        "args": {"query": "my query", "page_size": 20},
    }

def test_search_custom_limit():
    call = build_search_call("my query", limit=5)
    assert call["args"]["page_size"] == 5

def test_search_with_filter():
    call = build_search_call("query", filter_type="database")
    assert call["args"]["filter"] == {"property": "object", "value": "database"}

def test_create_required_fields():
    call = build_create_call(parent="page-id-123", title="New Page")
    assert call["tool"] == "create_page"
    assert call["args"]["parent_id"] == "page-id-123"
    assert call["args"]["properties"]["title"] == "New Page"

def test_create_with_body():
    call = build_create_call(parent="page-id-123", title="New Page", body="Content")
    assert "children" in call["args"]
```

**Setup** (`pyproject.toml`):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

### Rust

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn search_default_page_size() {
        let call = build_search_call("my query", &SearchOpts::default());
        assert_eq!(call.tool, "search");
        assert_eq!(call.args["page_size"], 20);
    }

    #[test]
    fn search_custom_limit() {
        let call = build_search_call("my query", &SearchOpts { limit: Some(5), ..Default::default() });
        assert_eq!(call.args["page_size"], 5);
    }
}
```

### Go

```go
func TestBuildSearchCall(t *testing.T) {
    tests := []struct {
        name     string
        query    string
        opts     SearchOpts
        wantTool string
        wantSize int
    }{
        {"default page size", "my query", SearchOpts{}, "search", 20},
        {"custom limit", "my query", SearchOpts{Limit: 5}, "search", 5},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            call := BuildSearchCall(tt.query, tt.opts)
            if call.Tool != tt.wantTool {
                t.Errorf("got tool %q, want %q", call.Tool, tt.wantTool)
            }
            if call.Args["page_size"] != tt.wantSize {
                t.Errorf("got page_size %d, want %d", call.Args["page_size"], tt.wantSize)
            }
        })
    }
}
```

---

## Output Formatting Tests

Verify the three output modes work correctly:

```typescript
describe("printOutput", () => {
  test("--json mode wraps string as text", () => {
    const output = captureStdout(() =>
      printOutput("hello", { json: true })
    );
    expect(JSON.parse(output)).toEqual({ text: "hello" });
  });

  test("--json mode passes objects through", () => {
    const output = captureStdout(() =>
      printOutput({ id: "123" }, { json: true })
    );
    expect(JSON.parse(output)).toEqual({ id: "123" });
  });

  test("--raw mode outputs string as-is", () => {
    const output = captureStdout(() =>
      printOutput("raw data", { raw: true })
    );
    expect(output).toBe("raw data");
  });
});
```

---

## Error Hint Tests

Verify hint rules match the right errors:

```typescript
describe("findHint", () => {
  test("matches 404 errors", () => {
    const err = new Error("Resource not found (404)");
    const hint = findHint(err);
    expect(hint).toContain("search");
  });

  test("matches auth errors", () => {
    const err = new Error("Unauthorized: invalid token");
    const hint = findHint(err);
    expect(hint).toContain("login");
  });

  test("returns undefined for unknown errors", () => {
    const err = new Error("Something completely unexpected");
    const hint = findHint(err);
    expect(hint).toBeUndefined();
  });

  test("scoped rules only match their command", () => {
    const err = new Error("Not found");
    const searchHint = findHint(err, "search");
    const fetchHint = findHint(err, "fetch");
    // Both may match the general not-found rule, or command-specific ones
    expect(searchHint).toBeDefined();
  });
});
```

---

## Integration Tests (Optional)

For complex CLIs, test end-to-end with a mock server:

```typescript
import { execSync } from "child_process";
import { createServer } from "./test-helpers/mock-server";

describe("CLI integration", () => {
  let server: ReturnType<typeof createServer>;

  beforeAll(async () => {
    server = await createServer({ port: 9999 });
  });

  afterAll(() => server.close());

  test("search returns results as JSON", () => {
    const output = execSync(
      "node ./dist/cli.js search 'test' --json",
      { env: { ...process.env, MYCLI_API_URL: "http://localhost:9999" } }
    ).toString();
    const result = JSON.parse(output);
    expect(result).toHaveProperty("results");
  });

  test("unknown ID returns structured error", () => {
    try {
      execSync("node ./dist/cli.js fetch bad-id --json", {
        env: { ...process.env, MYCLI_API_URL: "http://localhost:9999" },
      });
    } catch (e: any) {
      const error = JSON.parse(e.stderr.toString());
      expect(error).toHaveProperty("error");
      expect(error).toHaveProperty("hint");
    }
  });
});
```

---

## Test Coverage Strategy

Focus coverage on the layers that matter most:

| Layer | Target Coverage | Why |
|---|---|---|
| `buildXxxCall()` | High (90%+) | Core logic, easy to test |
| Output formatting | Medium (70%+) | Three modes, edge cases |
| Error hints | Medium (70%+) | Pattern matching correctness |
| Connection/lifecycle | Low (smoke test) | Thin glue, hard to unit test |
| CLI parsing | Low (smoke test) | Framework handles this |
