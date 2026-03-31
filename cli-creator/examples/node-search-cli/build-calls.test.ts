import { describe, test, expect } from "vitest";
import {
  buildSearchCall,
  buildFetchCall,
  buildCreateCall,
  buildUpdateCall,
  buildDeleteCall,
  buildQueryCall,
} from "./build-calls";

describe("buildSearchCall", () => {
  test("sets default page_size of 20", () => {
    const call = buildSearchCall("my query");
    expect(call).toEqual({
      tool: "search",
      args: { query: "my query", page_size: 20 },
    });
  });

  test("respects custom limit", () => {
    const call = buildSearchCall("my query", { limit: 5 });
    expect(call.args.page_size).toBe(5);
  });

  test("includes filter when provided", () => {
    const call = buildSearchCall("query", { filter: "database" });
    expect(call.args.filter).toEqual({
      property: "object",
      value: "database",
    });
  });

  test("omits filter when not provided", () => {
    const call = buildSearchCall("query");
    expect(call.args.filter).toBeUndefined();
  });
});

describe("buildFetchCall", () => {
  test("constructs basic fetch call", () => {
    const call = buildFetchCall("page-id-123");
    expect(call).toEqual({
      tool: "get_page",
      args: { page_id: "page-id-123" },
    });
  });

  test("includes children flag when requested", () => {
    const call = buildFetchCall("page-id-123", { includeChildren: true });
    expect(call.args.include_children).toBe(true);
  });
});

describe("buildCreateCall", () => {
  test("constructs call with required fields", () => {
    const call = buildCreateCall({
      parent: "parent-id",
      title: "New Page",
    });
    expect(call.tool).toBe("create_page");
    expect(call.args.parent_id).toBe("parent-id");
    expect(call.args.properties).toEqual({ title: "New Page" });
    expect(call.args.children).toBeUndefined();
  });

  test("includes children when body is provided", () => {
    const call = buildCreateCall({
      parent: "parent-id",
      title: "New Page",
      body: "Some content",
    });
    expect(call.args.children).toBeDefined();
    expect(call.args.children).toHaveLength(1);
  });
});

describe("buildUpdateCall", () => {
  test("updates title", () => {
    const call = buildUpdateCall({ id: "page-id", title: "Updated" });
    expect(call.tool).toBe("update_page");
    expect(call.args.page_id).toBe("page-id");
    expect(call.args.properties).toEqual({ title: "Updated" });
  });

  test("sets archived flag", () => {
    const call = buildUpdateCall({ id: "page-id", archived: true });
    expect(call.args.archived).toBe(true);
  });

  test("omits empty properties", () => {
    const call = buildUpdateCall({ id: "page-id", archived: false });
    expect(call.args.properties).toBeUndefined();
  });
});

describe("buildDeleteCall", () => {
  test("archives the page", () => {
    const call = buildDeleteCall("page-id");
    expect(call.tool).toBe("update_page");
    expect(call.args.archived).toBe(true);
  });
});

describe("buildQueryCall", () => {
  test("constructs basic query with defaults", () => {
    const call = buildQueryCall({ databaseId: "db-id" });
    expect(call).toEqual({
      tool: "query_database",
      args: { database_id: "db-id", page_size: 100 },
    });
  });

  test("includes sort when provided", () => {
    const call = buildQueryCall({
      databaseId: "db-id",
      sort: { property: "created", direction: "descending" },
    });
    expect(call.args.sorts).toEqual([
      { property: "created", direction: "descending" },
    ]);
  });

  test("includes filter when provided", () => {
    const filter = { property: "Status", select: { equals: "Done" } };
    const call = buildQueryCall({ databaseId: "db-id", filter });
    expect(call.args.filter).toEqual(filter);
  });

  test("respects custom limit", () => {
    const call = buildQueryCall({ databaseId: "db-id", limit: 10 });
    expect(call.args.page_size).toBe(10);
  });
});
