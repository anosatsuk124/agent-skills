"""Unit tests for storage.py -- uses tmp_path fixture, touches filesystem."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from code_clip.build_calls import StorageOp, build_copy_call, build_cut_call
from code_clip.errors import ClipboardError
from code_clip.storage import ClipboardStore


def make_store(tmp_path: Path) -> ClipboardStore:
    store_dir = tmp_path / ".code-clip"
    store = ClipboardStore(store_dir)
    store.init()
    return store


def write_entry(store: ClipboardStore, name: str, content: str, **kwargs) -> None:
    op = build_copy_call(name, content, **kwargs)
    store.write(op.params)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------

class TestInit:
    def test_creates_directory_structure(self, tmp_path):
        store_dir = tmp_path / ".code-clip"
        store = ClipboardStore(store_dir)
        store.init()
        assert (store_dir / "entries").is_dir()
        assert (store_dir / "index.json").exists()
        assert (store_dir / "stack.json").exists()

    def test_index_initial_structure(self, tmp_path):
        store = make_store(tmp_path)
        index = json.loads((store.store_dir / "index.json").read_text())
        assert index["version"] == 1
        assert index["entries"] == {}

    def test_idempotent(self, tmp_path):
        store = make_store(tmp_path)
        store.init()  # second call should not raise


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------

class TestWrite:
    def test_creates_entry_file(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "my-clip", "hello world")
        assert (store.store_dir / "entries" / "my-clip.json").exists()

    def test_entry_content(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "def foo(): pass")
        entry = json.loads((store.store_dir / "entries" / "clip.json").read_text())
        assert entry["content"] == "def foo(): pass"
        assert entry["name"] == "clip"

    def test_updates_index(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code")
        index = json.loads((store.store_dir / "index.json").read_text())
        assert "clip" in index["entries"]

    def test_rejects_duplicate_without_overwrite(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "first")
        with pytest.raises(ClipboardError, match="already exists"):
            write_entry(store, "clip", "second")

    def test_allows_overwrite(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "first")
        write_entry(store, "clip", "second", overwrite=True)
        entry = json.loads((store.store_dir / "entries" / "clip.json").read_text())
        assert entry["content"] == "second"

    def test_auto_push_to_stack(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", push=True)
        stack = json.loads((store.store_dir / "stack.json").read_text())
        assert "clip" in stack["stack"]

    def test_language_stored_in_metadata(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", language="rust")
        entry = json.loads((store.store_dir / "entries" / "clip.json").read_text())
        assert entry["metadata"]["language"] == "rust"

    def test_tags_stored(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", tags=["refactor", "test"])
        entry = json.loads((store.store_dir / "entries" / "clip.json").read_text())
        assert entry["metadata"]["tags"] == ["refactor", "test"]

    def test_invalid_name_raises(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ClipboardError, match="Invalid clipboard name"):
            store.write({"name": "my clip!", "content": "x", "tags": [], "operation": "copy", "push": False, "overwrite": False})

    def test_cut_operation_stored(self, tmp_path):
        store = make_store(tmp_path)
        op = build_cut_call("cut-clip", "remove me", source_file="src.py", line_start=5, line_end=10)
        store.write(op.params)
        entry = json.loads((store.store_dir / "entries" / "cut-clip.json").read_text())
        assert entry["metadata"]["operation"] == "cut"


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

class TestRead:
    def test_returns_content(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "hello world")
        result = store.read({"name": "clip", "pop": False, "strip_indent": False, "indent": None})
        assert result["content"] == "hello world"

    def test_nonexistent_raises(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ClipboardError, match="not found"):
            store.read({"name": "nonexistent", "pop": False, "strip_indent": False, "indent": None})

    def test_include_metadata(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", language="python")
        result = store.read({"name": "clip", "pop": False, "strip_indent": False, "indent": None, "include_metadata": True})
        assert "metadata" in result
        assert result["metadata"]["language"] == "python"

    def test_strip_indent(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "    def foo():\n        pass\n")
        result = store.read({"name": "clip", "pop": False, "strip_indent": True, "indent": None})
        assert result["content"].startswith("def ")

    def test_pop_removes_entry(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code")
        store.read({"name": "clip", "pop": True, "strip_indent": False, "indent": None})
        assert not (store.store_dir / "entries" / "clip.json").exists()


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    def test_removes_file_and_index(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code")
        store.delete({"name": "clip"})
        assert not (store.store_dir / "entries" / "clip.json").exists()
        index = json.loads((store.store_dir / "index.json").read_text())
        assert "clip" not in index["entries"]

    def test_nonexistent_raises(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ClipboardError, match="not found"):
            store.delete({"name": "missing"})

    def test_removes_from_stack(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", push=True)
        store.delete({"name": "clip"})
        stack = json.loads((store.store_dir / "stack.json").read_text())
        assert "clip" not in stack["stack"]


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

class TestClear:
    def test_clears_all(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1")
        write_entry(store, "b", "code2")
        result = store.clear({"tag": None})
        assert result["count"] == 2
        index = json.loads((store.store_dir / "index.json").read_text())
        assert index["entries"] == {}

    def test_clear_by_tag(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1", tags=["refactor"])
        write_entry(store, "b", "code2", tags=["other"])
        result = store.clear({"tag": "refactor"})
        assert result["count"] == 1
        index = json.loads((store.store_dir / "index.json").read_text())
        assert "b" in index["entries"]
        assert "a" not in index["entries"]


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

class TestList:
    def test_returns_all_entries(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1")
        write_entry(store, "b", "code2")
        result = store.list_({"sort": "name", "limit": 50})
        names = [e["name"] for e in result["entries"]]
        assert "a" in names and "b" in names

    def test_filter_by_tag(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1", tags=["refactor"])
        write_entry(store, "b", "code2", tags=["test"])
        result = store.list_({"tag": "refactor", "sort": "name", "limit": 50})
        names = [e["name"] for e in result["entries"]]
        assert names == ["a"]

    def test_filter_by_language(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1", language="python")
        write_entry(store, "b", "code2", language="rust")
        result = store.list_({"language": "python", "sort": "name", "limit": 50})
        names = [e["name"] for e in result["entries"]]
        assert names == ["a"]

    def test_sort_by_name(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "z-clip", "code")
        write_entry(store, "a-clip", "code")
        result = store.list_({"sort": "name", "limit": 50})
        names = [e["name"] for e in result["entries"]]
        assert names[0] == "a-clip"

    def test_limit(self, tmp_path):
        store = make_store(tmp_path)
        for i in range(5):
            write_entry(store, f"clip-{i}", f"code {i}")
        result = store.list_({"sort": "name", "limit": 3})
        assert len(result["entries"]) == 3


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_by_name(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "auth-func", "code")
        write_entry(store, "payment-func", "code")
        result = store.search({"query": "auth", "scope": "name", "limit": 20})
        names = [r["name"] for r in result["results"]]
        assert "auth-func" in names
        assert "payment-func" not in names

    def test_search_by_content(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip1", "def authenticate(): pass")
        write_entry(store, "clip2", "def process_payment(): pass")
        result = store.search({"query": "authenticate", "scope": "content", "limit": 20})
        names = [r["name"] for r in result["results"]]
        assert "clip1" in names
        assert "clip2" not in names

    def test_search_by_tag(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip1", "code", tags=["refactor"])
        write_entry(store, "clip2", "code", tags=["test"])
        result = store.search({"query": "refactor", "scope": "tag", "limit": 20})
        names = [r["name"] for r in result["results"]]
        assert "clip1" in names
        assert "clip2" not in names

    def test_search_all_scope(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "myquery-clip", "other code")
        write_entry(store, "other", "myquery content here")
        result = store.search({"query": "myquery", "scope": "all", "limit": 20})
        names = [r["name"] for r in result["results"]]
        assert "myquery-clip" in names
        assert "other" in names

    def test_filter_by_language(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "py-clip", "def foo(): pass", language="python")
        write_entry(store, "rs-clip", "fn foo() {}", language="rust")
        result = store.search({"query": "clip", "scope": "name", "language": "python", "limit": 20})
        names = [r["name"] for r in result["results"]]
        assert "py-clip" in names
        assert "rs-clip" not in names


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

class TestDiff:
    def test_diff_changed(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "before", "def foo():\n    return 1\n")
        write_entry(store, "after", "def foo():\n    return 2\n")
        result = store.diff({"name1": "before", "name2": "after", "context_lines": 3})
        assert result["changed"] is True
        assert "before" in result["diff"]
        assert "after" in result["diff"]

    def test_diff_no_change(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "same content\n")
        write_entry(store, "b", "same content\n")
        result = store.diff({"name1": "a", "name2": "b", "context_lines": 3})
        assert result["changed"] is False

    def test_diff_nonexistent_raises(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code")
        with pytest.raises(ClipboardError, match="not found"):
            store.diff({"name1": "a", "name2": "missing", "context_lines": 3})


# ---------------------------------------------------------------------------
# stack
# ---------------------------------------------------------------------------

class TestStack:
    def test_push_pop_ordering(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "first", "code1")
        write_entry(store, "second", "code2")
        store.stack_push({"name": "first"})
        store.stack_push({"name": "second"})
        # LIFO: second should be on top
        result = store.stack_pop({"peek": False})
        assert result["name"] == "second"

    def test_peek_does_not_remove(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code")
        store.stack_push({"name": "clip"})
        store.stack_pop({"peek": True})
        stack = json.loads((store.store_dir / "stack.json").read_text())
        assert "clip" in stack["stack"]

    def test_pop_empty_stack_raises(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ClipboardError, match="empty"):
            store.stack_pop({"peek": False})

    def test_push_nonexistent_raises(self, tmp_path):
        store = make_store(tmp_path)
        with pytest.raises(ClipboardError, match="not found"):
            store.stack_push({"name": "missing"})

    def test_stack_list(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1")
        write_entry(store, "b", "code2")
        store.stack_push({"name": "a"})
        store.stack_push({"name": "b"})
        result = store.stack_list({})
        names = [item["name"] for item in result["stack"]]
        assert names == ["b", "a"]


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_combines_content(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "part1", "line1")
        write_entry(store, "part2", "line2")
        result = store.merge({"target_name": "merged", "source_names": ["part1", "part2"], "separator": "\n", "delete_sources": False})
        assert result["target"] == "merged"
        merged = json.loads((store.store_dir / "entries" / "merged.json").read_text())
        assert "line1" in merged["content"]
        assert "line2" in merged["content"]

    def test_custom_separator(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "partA")
        write_entry(store, "b", "partB")
        store.merge({"target_name": "out", "source_names": ["a", "b"], "separator": "\n\n---\n\n", "delete_sources": False})
        entry = json.loads((store.store_dir / "entries" / "out.json").read_text())
        assert "---" in entry["content"]

    def test_delete_sources(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "x", "codeX")
        write_entry(store, "y", "codeY")
        store.merge({"target_name": "z", "source_names": ["x", "y"], "separator": "\n", "delete_sources": True})
        assert not (store.store_dir / "entries" / "x.json").exists()
        assert not (store.store_dir / "entries" / "y.json").exists()

    def test_nonexistent_source_raises(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code")
        with pytest.raises(ClipboardError, match="not found"):
            store.merge({"target_name": "out", "source_names": ["a", "missing"], "separator": "\n", "delete_sources": False})


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

class TestVerify:
    def test_verify_match(self, tmp_path):
        src = tmp_path / "src.py"
        src.write_text("line1\ndef foo():\n    pass\nline4\n", encoding="utf-8")
        store = make_store(tmp_path)
        write_entry(store, "clip", "def foo():\n    pass\n", source_file=str(src), line_start=2, line_end=3)
        result = store.verify({"name": "clip"})
        assert result["verified"] is True

    def test_verify_mismatch(self, tmp_path):
        src = tmp_path / "src.py"
        src.write_text("def foo():\n    return 1\n", encoding="utf-8")
        store = make_store(tmp_path)
        write_entry(store, "clip", "def foo():\n    return 99\n", source_file=str(src))
        result = store.verify({"name": "clip"})
        assert result["verified"] is False

    def test_verify_no_source_file(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "stdin code")
        result = store.verify({"name": "clip"})
        assert result["verified"] is None

    def test_verify_missing_source_file(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code", source_file="/nonexistent/path.py")
        result = store.verify({"name": "clip"})
        assert result["verified"] is False


# ---------------------------------------------------------------------------
# export / import
# ---------------------------------------------------------------------------

class TestExportImport:
    def test_export_import_roundtrip(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip1", "code1", language="python")
        write_entry(store, "clip2", "code2", language="rust")

        export_data = store.export({"output_file": None})
        assert len(export_data["entries"]) == 2

        # Import into fresh store
        store2 = ClipboardStore(tmp_path / ".code-clip-2")
        store2.init()
        import_path = tmp_path / "export.json"
        import_path.write_text(json.dumps(export_data), encoding="utf-8")
        result = store2.import_({"input_file": str(import_path), "overwrite": False})
        assert len(result["imported"]) == 2

    def test_export_to_file(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "code")
        out = tmp_path / "clips.json"
        result = store.export({"output_file": str(out)})
        assert result["exported_to"] == str(out)
        assert out.exists()

    def test_import_skips_existing_without_overwrite(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "original")
        export_data = store.export({"output_file": None})

        import_path = tmp_path / "export.json"
        import_path.write_text(json.dumps(export_data), encoding="utf-8")
        result = store.import_({"input_file": str(import_path), "overwrite": False})
        assert "clip" in result["skipped"]

    def test_import_with_overwrite(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "clip", "original")
        export_data = {"version": 1, "entries": [{"name": "clip", "content": "updated", "metadata": {"tags": [], "operation": "copy", "created_at": "2026-01-01T00:00:00+00:00", "size_bytes": 7, "line_count": 1, "checksum": "sha256:abc", "language": None, "source_file": None, "line_start": None, "line_end": None}}]}
        import_path = tmp_path / "export.json"
        import_path.write_text(json.dumps(export_data), encoding="utf-8")
        store.import_({"input_file": str(import_path), "overwrite": True})
        result = store.read({"name": "clip", "pop": False, "strip_indent": False, "indent": None})
        assert result["content"] == "updated"


# ---------------------------------------------------------------------------
# Index consistency
# ---------------------------------------------------------------------------

class TestIndexConsistency:
    def test_index_stays_in_sync_after_mutations(self, tmp_path):
        store = make_store(tmp_path)
        write_entry(store, "a", "code1")
        write_entry(store, "b", "code2")
        store.delete({"name": "a"})
        index = json.loads((store.store_dir / "index.json").read_text())
        assert "a" not in index["entries"]
        assert "b" in index["entries"]
