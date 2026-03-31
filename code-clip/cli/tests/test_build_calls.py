"""Unit tests for build_calls.py -- all pure functions, no I/O."""

import pytest
from code_clip.build_calls import (
    StorageOp,
    build_copy_call,
    build_cut_call,
    build_paste_call,
    build_list_call,
    build_show_call,
    build_delete_call,
    build_clear_call,
    build_search_call,
    build_diff_call,
    build_stack_push_call,
    build_stack_pop_call,
    build_stack_list_call,
    build_merge_call,
    build_verify_call,
    build_export_call,
    build_import_call,
    detect_language,
    compute_checksum,
    parse_line_range,
    transform_content,
)


# ---------------------------------------------------------------------------
# detect_language
# ---------------------------------------------------------------------------

class TestDetectLanguage:
    def test_python(self):
        assert detect_language("foo.py") == "python"

    def test_typescript(self):
        assert detect_language("bar.ts") == "typescript"

    def test_tsx(self):
        assert detect_language("Component.tsx") == "typescript"

    def test_javascript(self):
        assert detect_language("index.js") == "javascript"

    def test_rust(self):
        assert detect_language("main.rs") == "rust"

    def test_go(self):
        assert detect_language("server.go") == "go"

    def test_yaml(self):
        assert detect_language("config.yaml") == "yaml"
        assert detect_language("config.yml") == "yaml"

    def test_unknown_extension(self):
        assert detect_language("data.xyz") is None

    def test_no_extension(self):
        assert detect_language("Makefile") is None

    def test_absolute_path(self):
        assert detect_language("/home/user/project/src/auth.py") == "python"


# ---------------------------------------------------------------------------
# compute_checksum
# ---------------------------------------------------------------------------

class TestComputeChecksum:
    def test_format(self):
        cs = compute_checksum("hello")
        assert cs.startswith("sha256:")
        assert len(cs) == len("sha256:") + 64

    def test_deterministic(self):
        assert compute_checksum("abc") == compute_checksum("abc")

    def test_different_content_different_hash(self):
        assert compute_checksum("abc") != compute_checksum("def")

    def test_empty_string(self):
        cs = compute_checksum("")
        assert cs.startswith("sha256:")


# ---------------------------------------------------------------------------
# parse_line_range
# ---------------------------------------------------------------------------

class TestParseLineRange:
    def test_range(self):
        assert parse_line_range("10-25") == (10, 25)

    def test_single_line(self):
        assert parse_line_range("10") == (10, 10)

    def test_whitespace_stripped(self):
        assert parse_line_range("  5-10  ") == (5, 10)

    def test_invalid_text(self):
        with pytest.raises(ValueError):
            parse_line_range("abc")

    def test_invalid_range_text(self):
        with pytest.raises(ValueError):
            parse_line_range("abc-def")

    def test_zero_line(self):
        with pytest.raises(ValueError):
            parse_line_range("0")

    def test_end_before_start(self):
        with pytest.raises(ValueError):
            parse_line_range("20-10")


# ---------------------------------------------------------------------------
# transform_content
# ---------------------------------------------------------------------------

class TestTransformContent:
    def test_no_op(self):
        content = "    def foo():\n        pass\n"
        assert transform_content(content) == content

    def test_strip_indent(self):
        content = "    def foo():\n        pass\n"
        result = transform_content(content, strip_indent=True)
        assert result == "def foo():\n    pass\n"

    def test_strip_indent_mixed(self):
        content = "  line1\n    line2\n  line3\n"
        result = transform_content(content, strip_indent=True)
        assert result == "line1\n  line2\nline3\n"

    def test_indent(self):
        content = "def foo():\n    pass\n"
        result = transform_content(content, indent=4)
        assert result.startswith("    ")

    def test_strip_then_indent(self):
        content = "    def foo():\n        pass\n"
        result = transform_content(content, strip_indent=True, indent=2)
        assert result.startswith("  ")


# ---------------------------------------------------------------------------
# build_copy_call
# ---------------------------------------------------------------------------

class TestBuildCopyCall:
    def test_basic(self):
        op = build_copy_call("my-clip", "hello world")
        assert isinstance(op, StorageOp)
        assert op.action == "write"
        assert op.params["name"] == "my-clip"
        assert op.params["content"] == "hello world"
        assert op.params["operation"] == "copy"

    def test_default_tags_empty_list(self):
        op = build_copy_call("clip", "code")
        assert op.params["tags"] == []

    def test_with_tags(self):
        op = build_copy_call("clip", "code", tags=["refactor", "test"])
        assert op.params["tags"] == ["refactor", "test"]

    def test_auto_detect_language_from_file(self):
        op = build_copy_call("clip", "code", source_file="main.py")
        assert op.params["language"] == "python"

    def test_explicit_language_overrides_auto(self):
        op = build_copy_call("clip", "code", source_file="main.py", language="ruby")
        assert op.params["language"] == "ruby"

    def test_no_source_no_language(self):
        op = build_copy_call("clip", "code")
        assert op.params["language"] is None

    def test_with_line_range(self):
        op = build_copy_call("clip", "code", source_file="x.py", line_start=10, line_end=20)
        assert op.params["line_start"] == 10
        assert op.params["line_end"] == 20

    def test_overwrite_flag(self):
        op = build_copy_call("clip", "code", overwrite=True)
        assert op.params["overwrite"] is True

    def test_push_flag(self):
        op = build_copy_call("clip", "code", push=True)
        assert op.params["push"] is True

    def test_checksum_computed(self):
        op = build_copy_call("clip", "hello")
        assert op.params["checksum"].startswith("sha256:")

    def test_tags_list_is_copy(self):
        tags = ["a", "b"]
        op = build_copy_call("clip", "code", tags=tags)
        tags.append("c")
        assert op.params["tags"] == ["a", "b"]  # not mutated


# ---------------------------------------------------------------------------
# build_cut_call
# ---------------------------------------------------------------------------

class TestBuildCutCall:
    def test_operation_is_cut(self):
        op = build_cut_call("clip", "code")
        assert op.params["operation"] == "cut"

    def test_push_always_false(self):
        op = build_cut_call("clip", "code")
        assert op.params["push"] is False

    def test_auto_detect_language(self):
        op = build_cut_call("clip", "code", source_file="app.ts")
        assert op.params["language"] == "typescript"

    def test_checksum_matches_copy(self):
        content = "some code"
        cut_op = build_cut_call("clip", content)
        copy_op = build_copy_call("clip", content)
        assert cut_op.params["checksum"] == copy_op.params["checksum"]


# ---------------------------------------------------------------------------
# build_paste_call
# ---------------------------------------------------------------------------

class TestBuildPasteCall:
    def test_basic(self):
        op = build_paste_call("clip")
        assert op.action == "read"
        assert op.params["name"] == "clip"
        assert op.params["pop"] is False

    def test_with_pop(self):
        op = build_paste_call("clip", pop=True)
        assert op.params["pop"] is True

    def test_strip_indent(self):
        op = build_paste_call("clip", strip_indent=True)
        assert op.params["strip_indent"] is True

    def test_indent(self):
        op = build_paste_call("clip", indent=4)
        assert op.params["indent"] == 4


# ---------------------------------------------------------------------------
# build_list_call
# ---------------------------------------------------------------------------

class TestBuildListCall:
    def test_defaults(self):
        op = build_list_call()
        assert op.action == "list"
        assert op.params["sort"] == "created"
        assert op.params["limit"] == 50
        assert op.params["tag"] is None
        assert op.params["language"] is None

    def test_with_tag_filter(self):
        op = build_list_call(tag="refactor")
        assert op.params["tag"] == "refactor"

    def test_with_language_filter(self):
        op = build_list_call(language="python")
        assert op.params["language"] == "python"

    def test_custom_sort_and_limit(self):
        op = build_list_call(sort="name", limit=10)
        assert op.params["sort"] == "name"
        assert op.params["limit"] == 10


# ---------------------------------------------------------------------------
# build_show_call
# ---------------------------------------------------------------------------

class TestBuildShowCall:
    def test_includes_metadata(self):
        op = build_show_call("my-clip")
        assert op.action == "read"
        assert op.params["name"] == "my-clip"
        assert op.params.get("include_metadata") is True

    def test_pop_is_false(self):
        op = build_show_call("clip")
        assert op.params["pop"] is False


# ---------------------------------------------------------------------------
# build_delete_call
# ---------------------------------------------------------------------------

class TestBuildDeleteCall:
    def test_basic(self):
        op = build_delete_call("clip")
        assert op.action == "delete"
        assert op.params["name"] == "clip"


# ---------------------------------------------------------------------------
# build_clear_call
# ---------------------------------------------------------------------------

class TestBuildClearCall:
    def test_clear_all(self):
        op = build_clear_call()
        assert op.action == "clear"
        assert op.params["tag"] is None

    def test_clear_by_tag(self):
        op = build_clear_call(tag="refactor")
        assert op.params["tag"] == "refactor"


# ---------------------------------------------------------------------------
# build_search_call
# ---------------------------------------------------------------------------

class TestBuildSearchCall:
    def test_defaults(self):
        op = build_search_call("hello")
        assert op.action == "search"
        assert op.params["query"] == "hello"
        assert op.params["scope"] == "all"
        assert op.params["limit"] == 20

    def test_name_scope(self):
        op = build_search_call("auth", scope="name")
        assert op.params["scope"] == "name"

    def test_content_scope(self):
        op = build_search_call("def foo", scope="content")
        assert op.params["scope"] == "content"

    def test_with_language(self):
        op = build_search_call("async", language="python")
        assert op.params["language"] == "python"


# ---------------------------------------------------------------------------
# build_diff_call
# ---------------------------------------------------------------------------

class TestBuildDiffCall:
    def test_basic(self):
        op = build_diff_call("before", "after")
        assert op.action == "diff"
        assert op.params["name1"] == "before"
        assert op.params["name2"] == "after"
        assert op.params["context_lines"] == 3

    def test_custom_context(self):
        op = build_diff_call("a", "b", context_lines=5)
        assert op.params["context_lines"] == 5


# ---------------------------------------------------------------------------
# Stack operations
# ---------------------------------------------------------------------------

class TestStackCalls:
    def test_push(self):
        op = build_stack_push_call("my-clip")
        assert op.action == "stack_push"
        assert op.params["name"] == "my-clip"

    def test_pop_default(self):
        op = build_stack_pop_call()
        assert op.action == "stack_pop"
        assert op.params["peek"] is False
        assert op.params["name"] is None

    def test_pop_peek(self):
        op = build_stack_pop_call(peek=True)
        assert op.params["peek"] is True

    def test_pop_with_name(self):
        op = build_stack_pop_call(name="saved")
        assert op.params["name"] == "saved"

    def test_list(self):
        op = build_stack_list_call()
        assert op.action == "stack_list"
        assert op.params == {}


# ---------------------------------------------------------------------------
# build_merge_call
# ---------------------------------------------------------------------------

class TestBuildMergeCall:
    def test_basic(self):
        op = build_merge_call("combined", ["part1", "part2"])
        assert op.action == "merge"
        assert op.params["target_name"] == "combined"
        assert op.params["source_names"] == ["part1", "part2"]
        assert op.params["separator"] == "\n"
        assert op.params["delete_sources"] is False

    def test_custom_separator(self):
        op = build_merge_call("out", ["a", "b"], separator="\n\n")
        assert op.params["separator"] == "\n\n"

    def test_delete_sources(self):
        op = build_merge_call("out", ["a", "b"], delete_sources=True)
        assert op.params["delete_sources"] is True

    def test_source_names_list_is_copy(self):
        names = ["a", "b"]
        op = build_merge_call("out", names)
        names.append("c")
        assert op.params["source_names"] == ["a", "b"]


# ---------------------------------------------------------------------------
# build_verify_call
# ---------------------------------------------------------------------------

class TestBuildVerifyCall:
    def test_basic(self):
        op = build_verify_call("clip")
        assert op.action == "verify"
        assert op.params["name"] == "clip"


# ---------------------------------------------------------------------------
# build_export_call / build_import_call
# ---------------------------------------------------------------------------

class TestExportImportCalls:
    def test_export_no_file(self):
        op = build_export_call()
        assert op.action == "export"
        assert op.params["output_file"] is None

    def test_export_with_file(self):
        op = build_export_call(output_file="clips.json")
        assert op.params["output_file"] == "clips.json"

    def test_import_basic(self):
        op = build_import_call("clips.json")
        assert op.action == "import_"
        assert op.params["input_file"] == "clips.json"
        assert op.params["overwrite"] is False

    def test_import_overwrite(self):
        op = build_import_call("clips.json", overwrite=True)
        assert op.params["overwrite"] is True
