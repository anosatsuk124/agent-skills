"""Tests for build_calls pure functions."""

from build_calls import (
    build_search_call,
    build_fetch_call,
    build_create_call,
    build_update_call,
    build_delete_call,
    build_query_call,
)


# --- Search ---


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


def test_search_without_filter():
    call = build_search_call("query")
    assert "filter" not in call["args"]


# --- Fetch ---


def test_fetch_basic():
    call = build_fetch_call("page-id-123")
    assert call == {
        "tool": "get_page",
        "args": {"page_id": "page-id-123"},
    }


def test_fetch_with_children():
    call = build_fetch_call("page-id-123", include_children=True)
    assert call["args"]["include_children"] is True


# --- Create ---


def test_create_required_fields():
    call = build_create_call(parent="parent-id", title="New Page")
    assert call["tool"] == "create_page"
    assert call["args"]["parent_id"] == "parent-id"
    assert call["args"]["properties"] == {"title": "New Page"}
    assert "children" not in call["args"]


def test_create_with_body():
    call = build_create_call(parent="parent-id", title="New Page", body="Content")
    assert "children" in call["args"]
    assert len(call["args"]["children"]) == 1


# --- Update ---


def test_update_title():
    call = build_update_call("page-id", title="Updated")
    assert call["tool"] == "update_page"
    assert call["args"]["page_id"] == "page-id"
    assert call["args"]["properties"] == {"title": "Updated"}


def test_update_archived():
    call = build_update_call("page-id", archived=True)
    assert call["args"]["archived"] is True


def test_update_no_empty_properties():
    call = build_update_call("page-id", archived=False)
    assert "properties" not in call["args"]


# --- Delete ---


def test_delete_archives_page():
    call = build_delete_call("page-id")
    assert call["tool"] == "update_page"
    assert call["args"]["archived"] is True


# --- Database Query ---


def test_query_basic():
    call = build_query_call("db-id")
    assert call == {
        "tool": "query_database",
        "args": {"database_id": "db-id", "page_size": 100},
    }


def test_query_with_sort():
    call = build_query_call(
        "db-id", sort_property="created", sort_direction="descending"
    )
    assert call["args"]["sorts"] == [
        {"property": "created", "direction": "descending"}
    ]


def test_query_with_filter():
    f = {"property": "Status", "select": {"equals": "Done"}}
    call = build_query_call("db-id", filter=f)
    assert call["args"]["filter"] == f


def test_query_custom_limit():
    call = build_query_call("db-id", limit=10)
    assert call["args"]["page_size"] == 10
