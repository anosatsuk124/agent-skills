"""
File-based clipboard storage layer.

Directory layout under .code-clip/:
    index.json        -- denormalized metadata index for fast list/search
    entries/<name>.json -- one JSON file per clipboard entry
    stack.json        -- ordered stack (list of entry names, index 0 = top)
"""

from __future__ import annotations

import difflib
import fcntl
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .build_calls import StorageOp, compute_checksum, transform_content
from .errors import ClipboardError

_INDEX_FILE = "index.json"
_STACK_FILE = "stack.json"
_ENTRIES_DIR = "entries"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _entry_path(store_dir: Path, name: str) -> Path:
    return store_dir / _ENTRIES_DIR / f"{name}.json"


def _validate_name(name: str) -> None:
    if not name:
        raise ClipboardError("Name cannot be empty", hint="Provide a non-empty clipboard name.")
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", name):
        raise ClipboardError(
            f"Invalid clipboard name '{name}'",
            why="Names may only contain letters, digits, hyphens, underscores, and dots.",
            hint="Use a name like 'auth-func' or 'my_snippet_v2'.",
        )


class ClipboardStore:
    """Thread-safe, file-backed clipboard store."""

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = store_dir
        self._entries_dir = store_dir / _ENTRIES_DIR
        self._index_file = store_dir / _INDEX_FILE
        self._stack_file = store_dir / _STACK_FILE

    def init(self) -> None:
        """Create directory structure if it does not exist."""
        self._entries_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_file.exists():
            self._write_json(self._index_file, {"version": 1, "entries": {}})
        if not self._stack_file.exists():
            self._write_json(self._stack_file, {"stack": []})

    # ------------------------------------------------------------------
    # Low-level JSON helpers with locking
    # ------------------------------------------------------------------

    def _read_json(self, path: Path) -> Any:
        with open(path, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                return json.load(f)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def _write_json(self, path: Path, data: Any) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        tmp.replace(path)  # atomic rename

    def _read_index(self) -> dict[str, Any]:
        if not self._index_file.exists():
            return {"version": 1, "entries": {}}
        return self._read_json(self._index_file)

    def _write_index(self, index: dict[str, Any]) -> None:
        self._write_json(self._index_file, index)

    def _read_stack(self) -> list[str]:
        if not self._stack_file.exists():
            return []
        data = self._read_json(self._stack_file)
        return data.get("stack", [])

    def _write_stack(self, stack: list[str]) -> None:
        self._write_json(self._stack_file, {"stack": stack})

    # ------------------------------------------------------------------
    # Write (copy / cut)
    # ------------------------------------------------------------------

    def write(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        _validate_name(name)
        content = params["content"]
        overwrite = params.get("overwrite", False)
        push = params.get("push", False)

        self.init()
        entry_path = _entry_path(self.store_dir, name)

        if entry_path.exists() and not overwrite:
            raise ClipboardError(
                f"Clipboard '{name}' already exists",
                why="A clipboard entry with this name was previously saved.",
                hint=f"Use --overwrite to replace it, or choose a different name.",
            )

        entry: dict[str, Any] = {
            "name": name,
            "content": content,
            "metadata": {
                "source_file": params.get("source_file"),
                "line_start": params.get("line_start"),
                "line_end": params.get("line_end"),
                "language": params.get("language"),
                "operation": params.get("operation", "copy"),
                "tags": params.get("tags", []),
                "created_at": _now_iso(),
                "size_bytes": len(content.encode("utf-8")),
                "line_count": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
                "checksum": params.get("checksum", compute_checksum(content)),
            },
        }
        self._write_json(entry_path, entry)

        # Update index
        index = self._read_index()
        index["entries"][name] = {
            "language": entry["metadata"]["language"],
            "tags": entry["metadata"]["tags"],
            "operation": entry["metadata"]["operation"],
            "source_file": entry["metadata"]["source_file"],
            "created_at": entry["metadata"]["created_at"],
            "line_count": entry["metadata"]["line_count"],
            "size_bytes": entry["metadata"]["size_bytes"],
        }
        self._write_index(index)

        if push:
            stack = self._read_stack()
            stack.insert(0, name)
            self._write_stack(stack)

        return {"name": name, "operation": entry["metadata"]["operation"]}

    # ------------------------------------------------------------------
    # Read (paste / show)
    # ------------------------------------------------------------------

    def read(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        pop = params.get("pop", False)
        strip_indent = params.get("strip_indent", False)
        indent = params.get("indent")
        include_metadata = params.get("include_metadata", False)

        self.init()
        entry_path = _entry_path(self.store_dir, name)
        if not entry_path.exists():
            raise ClipboardError(
                f"Clipboard '{name}' not found",
                hint=f"Run `code-clip list --json` to see available clipboards.",
            )

        entry = self._read_json(entry_path)
        content = entry["content"]

        if strip_indent or indent is not None:
            content = transform_content(content, strip_indent=strip_indent, indent=indent)

        if pop:
            self._delete_entry(name)

        result: dict[str, Any] = {"name": name, "content": content}
        if include_metadata:
            result["metadata"] = entry.get("metadata", {})
        return result

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def _delete_entry(self, name: str) -> None:
        entry_path = _entry_path(self.store_dir, name)
        if entry_path.exists():
            entry_path.unlink()
        index = self._read_index()
        index["entries"].pop(name, None)
        self._write_index(index)
        # Remove from stack if present
        stack = self._read_stack()
        if name in stack:
            stack = [n for n in stack if n != name]
            self._write_stack(stack)

    def delete(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        self.init()
        entry_path = _entry_path(self.store_dir, name)
        if not entry_path.exists():
            raise ClipboardError(
                f"Clipboard '{name}' not found",
                hint=f"Run `code-clip list --json` to see available clipboards.",
            )
        self._delete_entry(name)
        return {"deleted": name}

    # ------------------------------------------------------------------
    # Clear
    # ------------------------------------------------------------------

    def clear(self, params: dict[str, Any]) -> dict[str, Any]:
        tag = params.get("tag")
        self.init()
        index = self._read_index()
        deleted = []
        for name, meta in list(index["entries"].items()):
            if tag is None or tag in meta.get("tags", []):
                entry_path = _entry_path(self.store_dir, name)
                if entry_path.exists():
                    entry_path.unlink()
                deleted.append(name)
        for name in deleted:
            index["entries"].pop(name, None)
        self._write_index(index)
        if deleted:
            stack = self._read_stack()
            stack = [n for n in stack if n not in deleted]
            self._write_stack(stack)
        return {"deleted": deleted, "count": len(deleted)}

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_(self, params: dict[str, Any]) -> dict[str, Any]:
        tag = params.get("tag")
        language = params.get("language")
        sort = params.get("sort", "created")
        limit = params.get("limit", 50)

        self.init()
        index = self._read_index()
        entries = []
        for name, meta in index["entries"].items():
            if tag and tag not in meta.get("tags", []):
                continue
            if language and meta.get("language") != language:
                continue
            entries.append({"name": name, **meta})

        if sort == "name":
            entries.sort(key=lambda e: e["name"])
        elif sort == "language":
            entries.sort(key=lambda e: (e.get("language") or "", e["name"]))
        else:  # "created" (default)
            entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)

        entries = entries[:limit]
        return {"entries": entries, "total": len(entries)}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params["query"].lower()
        scope = params.get("scope", "all")
        language = params.get("language")
        limit = params.get("limit", 20)

        self.init()
        index = self._read_index()
        results = []

        for name, meta in index["entries"].items():
            if language and meta.get("language") != language:
                continue

            matched = False
            if scope in ("name", "all") and query in name.lower():
                matched = True
            if not matched and scope in ("tag", "all"):
                if any(query in t.lower() for t in meta.get("tags", [])):
                    matched = True
            if not matched and scope in ("content", "all"):
                entry_path = _entry_path(self.store_dir, name)
                if entry_path.exists():
                    entry = self._read_json(entry_path)
                    if query in entry.get("content", "").lower():
                        matched = True

            if matched:
                results.append({"name": name, **meta})

        results = results[:limit]
        return {"results": results, "total": len(results)}

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def diff(self, params: dict[str, Any]) -> dict[str, Any]:
        name1 = params["name1"]
        name2 = params["name2"]
        context_lines = params.get("context_lines", 3)

        for name in (name1, name2):
            if not _entry_path(self.store_dir, name).exists():
                raise ClipboardError(
                    f"Clipboard '{name}' not found",
                    hint=f"Run `code-clip list --json` to see available clipboards.",
                )

        entry1 = self._read_json(_entry_path(self.store_dir, name1))
        entry2 = self._read_json(_entry_path(self.store_dir, name2))

        lines1 = entry1["content"].splitlines(keepends=True)
        lines2 = entry2["content"].splitlines(keepends=True)

        unified = list(
            difflib.unified_diff(
                lines1,
                lines2,
                fromfile=name1,
                tofile=name2,
                n=context_lines,
            )
        )
        return {
            "name1": name1,
            "name2": name2,
            "diff": "".join(unified),
            "changed": len(unified) > 0,
        }

    # ------------------------------------------------------------------
    # Stack operations
    # ------------------------------------------------------------------

    def stack_push(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        self.init()
        if not _entry_path(self.store_dir, name).exists():
            raise ClipboardError(
                f"Clipboard '{name}' not found",
                hint=f"Run `code-clip list --json` to see available clipboards.",
            )
        stack = self._read_stack()
        stack.insert(0, name)
        self._write_stack(stack)
        return {"pushed": name, "stack_size": len(stack)}

    def stack_pop(self, params: dict[str, Any]) -> dict[str, Any]:
        peek = params.get("peek", False)
        rename = params.get("name")

        self.init()
        stack = self._read_stack()
        if not stack:
            raise ClipboardError(
                "Stack is empty",
                hint="Use `code-clip copy <name> --push` to push items onto the stack.",
            )

        top_name = stack[0]
        entry_path = _entry_path(self.store_dir, top_name)
        if not entry_path.exists():
            # Stale stack entry — remove it
            stack.pop(0)
            self._write_stack(stack)
            raise ClipboardError(
                f"Stack top '{top_name}' no longer exists",
                hint="The clipboard entry was deleted. Try again.",
            )

        entry = self._read_json(entry_path)

        if not peek:
            stack.pop(0)
            self._write_stack(stack)
            if rename and rename != top_name:
                # Rename the entry
                new_path = _entry_path(self.store_dir, rename)
                entry["name"] = rename
                self._write_json(new_path, entry)
                entry_path.unlink()
                index = self._read_index()
                meta = index["entries"].pop(top_name, {})
                index["entries"][rename] = meta
                self._write_index(index)
                top_name = rename

        return {"name": top_name, "content": entry["content"], "remaining": len(stack)}

    def stack_list(self, params: dict[str, Any]) -> dict[str, Any]:
        self.init()
        stack = self._read_stack()
        items = []
        for name in stack:
            entry_path = _entry_path(self.store_dir, name)
            if entry_path.exists():
                entry = self._read_json(entry_path)
                items.append({
                    "name": name,
                    "language": entry["metadata"].get("language"),
                    "line_count": entry["metadata"].get("line_count"),
                })
            else:
                items.append({"name": name, "stale": True})
        return {"stack": items, "size": len(items)}

    # ------------------------------------------------------------------
    # Merge
    # ------------------------------------------------------------------

    def merge(self, params: dict[str, Any]) -> dict[str, Any]:
        target_name = params["target_name"]
        source_names = params["source_names"]
        separator = params.get("separator", "\n")
        delete_sources = params.get("delete_sources", False)

        _validate_name(target_name)
        self.init()

        parts = []
        for name in source_names:
            entry_path = _entry_path(self.store_dir, name)
            if not entry_path.exists():
                raise ClipboardError(
                    f"Clipboard '{name}' not found",
                    hint=f"Run `code-clip list --json` to see available clipboards.",
                )
            entry = self._read_json(entry_path)
            parts.append(entry["content"])

        merged_content = separator.join(parts)
        write_params = {
            "name": target_name,
            "content": merged_content,
            "operation": "copy",
            "tags": [],
            "overwrite": True,
            "push": False,
            "checksum": compute_checksum(merged_content),
        }
        self.write(write_params)

        if delete_sources:
            for name in source_names:
                self._delete_entry(name)

        return {"target": target_name, "sources": source_names, "line_count": merged_content.count("\n")}

    # ------------------------------------------------------------------
    # Verify
    # ------------------------------------------------------------------

    def verify(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params["name"]
        self.init()
        entry_path = _entry_path(self.store_dir, name)
        if not entry_path.exists():
            raise ClipboardError(
                f"Clipboard '{name}' not found",
                hint=f"Run `code-clip list --json` to see available clipboards.",
            )

        entry = self._read_json(entry_path)
        meta = entry.get("metadata", {})
        source_file = meta.get("source_file")
        line_start = meta.get("line_start")
        line_end = meta.get("line_end")
        stored_checksum = meta.get("checksum", "")

        if not source_file:
            return {
                "name": name,
                "verified": None,
                "reason": "No source file recorded; snippet was from stdin.",
            }

        source_path = Path(source_file)
        if not source_path.exists():
            return {
                "name": name,
                "verified": False,
                "reason": f"Source file '{source_file}' no longer exists.",
            }

        lines = source_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if line_start is not None and line_end is not None:
            # line numbers are 1-based
            current_content = "".join(lines[line_start - 1 : line_end])
        else:
            current_content = "".join(lines)

        current_checksum = compute_checksum(current_content)
        if current_checksum == stored_checksum:
            return {"name": name, "verified": True, "reason": "Source content matches stored snippet."}
        else:
            return {
                "name": name,
                "verified": False,
                "reason": "Source content has changed since snippet was captured.",
                "stored_checksum": stored_checksum,
                "current_checksum": current_checksum,
            }

    # ------------------------------------------------------------------
    # Export / Import
    # ------------------------------------------------------------------

    def export(self, params: dict[str, Any]) -> dict[str, Any]:
        output_file = params.get("output_file")
        self.init()
        index = self._read_index()
        all_entries = []
        for name in index["entries"]:
            entry_path = _entry_path(self.store_dir, name)
            if entry_path.exists():
                all_entries.append(self._read_json(entry_path))

        export_data = {
            "version": 1,
            "exported_at": _now_iso(),
            "stack": self._read_stack(),
            "entries": all_entries,
        }

        if output_file:
            out_path = Path(output_file)
            out_path.write_text(json.dumps(export_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            return {"exported_to": str(out_path), "count": len(all_entries)}
        else:
            return export_data

    def import_(self, params: dict[str, Any]) -> dict[str, Any]:
        input_file = params["input_file"]
        overwrite = params.get("overwrite", False)
        self.init()

        in_path = Path(input_file)
        if not in_path.exists():
            raise ClipboardError(
                f"Import file '{input_file}' not found",
                hint="Provide the path to a file created with `code-clip export`.",
            )

        data = json.loads(in_path.read_text(encoding="utf-8"))
        imported = []
        skipped = []

        for entry in data.get("entries", []):
            name = entry["name"]
            entry_path = _entry_path(self.store_dir, name)
            if entry_path.exists() and not overwrite:
                skipped.append(name)
                continue
            self._write_json(entry_path, entry)
            index = self._read_index()
            meta = entry.get("metadata", {})
            index["entries"][name] = {
                "language": meta.get("language"),
                "tags": meta.get("tags", []),
                "operation": meta.get("operation", "copy"),
                "source_file": meta.get("source_file"),
                "created_at": meta.get("created_at"),
                "line_count": meta.get("line_count"),
                "size_bytes": meta.get("size_bytes"),
            }
            self._write_index(index)
            imported.append(name)

        if "stack" in data:
            self._write_stack(data["stack"])

        return {"imported": imported, "skipped": skipped}

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def execute(self, op: StorageOp) -> Any:
        dispatch = {
            "write": self.write,
            "read": self.read,
            "delete": self.delete,
            "clear": self.clear,
            "list": self.list_,
            "search": self.search,
            "diff": self.diff,
            "stack_push": self.stack_push,
            "stack_pop": self.stack_pop,
            "stack_list": self.stack_list,
            "merge": self.merge,
            "verify": self.verify,
            "export": self.export,
            "import_": self.import_,
        }
        handler = dispatch.get(op.action)
        if handler is None:
            raise ClipboardError(f"Unknown action '{op.action}'")
        return handler(op.params)
