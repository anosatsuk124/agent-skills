"""
Pure functions that transform CLI arguments into API call parameters.
No I/O, no side effects -- easy to test without mocking.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ApiCall:
    tool: str
    args: dict[str, Any]


# --- Search ---


def build_search_call(
    query: str,
    *,
    limit: int | None = None,
    filter_type: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "query": query,
        "page_size": limit or 20,
    }
    if filter_type:
        args["filter"] = {"property": "object", "value": filter_type}
    return {"tool": "search", "args": args}


# --- Fetch ---


def build_fetch_call(
    page_id: str,
    *,
    include_children: bool = False,
) -> dict[str, Any]:
    args: dict[str, Any] = {"page_id": page_id}
    if include_children:
        args["include_children"] = True
    return {"tool": "get_page", "args": args}


# --- Create ---


def build_create_call(
    *,
    parent: str,
    title: str,
    body: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "parent_id": parent,
        "properties": {"title": title},
    }
    if body:
        args["children"] = [
            {
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": body}}],
                },
            }
        ]
    return {"tool": "create_page", "args": args}


# --- Update ---


def build_update_call(
    page_id: str,
    *,
    title: str | None = None,
    archived: bool | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {"page_id": page_id}
    properties: dict[str, Any] = {}

    if title is not None:
        properties["title"] = title
    if properties:
        args["properties"] = properties
    if archived is not None:
        args["archived"] = archived

    return {"tool": "update_page", "args": args}


# --- Delete (Archive) ---


def build_delete_call(page_id: str) -> dict[str, Any]:
    return build_update_call(page_id, archived=True)


# --- Database Query ---


def build_query_call(
    database_id: str,
    *,
    filter: dict[str, Any] | None = None,
    sort_property: str | None = None,
    sort_direction: str = "ascending",
    limit: int | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {
        "database_id": database_id,
        "page_size": limit or 100,
    }
    if filter:
        args["filter"] = filter
    if sort_property:
        args["sorts"] = [
            {"property": sort_property, "direction": sort_direction}
        ]
    return {"tool": "query_database", "args": args}
