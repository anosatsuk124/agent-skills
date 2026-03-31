/**
 * Pure functions that transform CLI arguments into API call parameters.
 * No I/O, no side effects -- easy to test without mocking.
 */

export interface ApiCall {
  tool: string;
  args: Record<string, unknown>;
}

// --- Search ---

export interface SearchOptions {
  limit?: number;
  filter?: "page" | "database";
}

export function buildSearchCall(query: string, opts: SearchOptions = {}): ApiCall {
  return {
    tool: "search",
    args: {
      query,
      page_size: opts.limit ?? 20,
      ...(opts.filter && {
        filter: { property: "object", value: opts.filter },
      }),
    },
  };
}

// --- Fetch ---

export interface FetchOptions {
  includeChildren?: boolean;
}

export function buildFetchCall(id: string, opts: FetchOptions = {}): ApiCall {
  return {
    tool: "get_page",
    args: {
      page_id: id,
      ...(opts.includeChildren && { include_children: true }),
    },
  };
}

// --- Create ---

export interface CreateOptions {
  parent: string;
  title: string;
  body?: string;
}

export function buildCreateCall(opts: CreateOptions): ApiCall {
  return {
    tool: "create_page",
    args: {
      parent_id: opts.parent,
      properties: {
        title: opts.title,
      },
      ...(opts.body && {
        children: [
          {
            type: "paragraph",
            paragraph: {
              rich_text: [{ type: "text", text: { content: opts.body } }],
            },
          },
        ],
      }),
    },
  };
}

// --- Update ---

export interface UpdateOptions {
  id: string;
  title?: string;
  archived?: boolean;
}

export function buildUpdateCall(opts: UpdateOptions): ApiCall {
  const properties: Record<string, unknown> = {};
  if (opts.title !== undefined) {
    properties.title = opts.title;
  }

  return {
    tool: "update_page",
    args: {
      page_id: opts.id,
      ...(Object.keys(properties).length > 0 && { properties }),
      ...(opts.archived !== undefined && { archived: opts.archived }),
    },
  };
}

// --- Delete (Archive) ---

export function buildDeleteCall(id: string): ApiCall {
  return buildUpdateCall({ id, archived: true });
}

// --- Database Query ---

export interface QueryOptions {
  databaseId: string;
  filter?: Record<string, unknown>;
  sort?: { property: string; direction: "ascending" | "descending" };
  limit?: number;
}

export function buildQueryCall(opts: QueryOptions): ApiCall {
  return {
    tool: "query_database",
    args: {
      database_id: opts.databaseId,
      ...(opts.filter && { filter: opts.filter }),
      ...(opts.sort && {
        sorts: [
          { property: opts.sort.property, direction: opts.sort.direction },
        ],
      }),
      page_size: opts.limit ?? 100,
    },
  };
}
