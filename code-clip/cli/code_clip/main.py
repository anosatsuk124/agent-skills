"""
code-clip -- Multi-clipboard CLI for code snippets.
Optimized for coding agents; equally usable by humans.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List, Optional

import typer

from .build_calls import (
    build_clear_call,
    build_copy_call,
    build_cut_call,
    build_delete_call,
    build_diff_call,
    build_export_call,
    build_import_call,
    build_list_call,
    build_merge_call,
    build_paste_call,
    build_search_call,
    build_show_call,
    build_stack_list_call,
    build_stack_pop_call,
    build_stack_push_call,
    build_verify_call,
    parse_line_range,
)
from .errors import ClipboardError, exit_with_error
from .output import print_result
from .storage import ClipboardStore

app = typer.Typer(
    name="code-clip",
    help="Multi-clipboard for code snippets. Named, tagged, searchable. Optimized for coding agents.",
    no_args_is_help=True,
    add_completion=False,
)
stack_app = typer.Typer(help="Stack-based LIFO clipboard operations.", no_args_is_help=True)
app.add_typer(stack_app, name="stack")


# ---------------------------------------------------------------------------
# Context helpers
# ---------------------------------------------------------------------------

def _get_store(store_dir: Optional[str]) -> ClipboardStore:
    """Resolve storage directory and return a ClipboardStore."""
    path = Path(store_dir) if store_dir else Path.cwd() / ".code-clip"
    return ClipboardStore(path)


def _read_stdin_or_file(
    file: Optional[str],
    lines_spec: Optional[str],
    json_mode: bool,
) -> tuple[str, Optional[int], Optional[int]]:
    """
    Read content from --file (with optional --lines) or from stdin.
    Returns (content, line_start, line_end).
    """
    line_start: Optional[int] = None
    line_end: Optional[int] = None

    if file:
        file_path = Path(file)
        if not file_path.exists():
            err = ClipboardError(
                f"File '{file}' not found",
                hint="Check the file path and try again.",
            )
            exit_with_error(err, json_mode=json_mode)
        all_lines = file_path.read_text(encoding="utf-8").splitlines(keepends=True)
        if lines_spec:
            try:
                line_start, line_end = parse_line_range(lines_spec)
            except ValueError as e:
                err = ClipboardError(str(e))
                exit_with_error(err, json_mode=json_mode)
            content = "".join(all_lines[line_start - 1 : line_end])
        else:
            content = "".join(all_lines)
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        typer.echo("Error: provide content via --file or stdin pipe.", err=True)
        raise typer.Exit(1)

    return content, line_start, line_end


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------

@app.command()
def copy(
    name: str = typer.Argument(..., help="Clipboard name (letters, digits, hyphens, underscores, dots)."),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Source file path (reads stdin if omitted)."),
    lines: Optional[str] = typer.Option(None, "--lines", "-l", help="Line range, e.g. '10-25' or '10'."),
    language: Optional[str] = typer.Option(None, "--lang", help="Language identifier (auto-detected from file extension if omitted)."),
    tags: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tag(s) for categorization (repeatable)."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite if name already exists."),
    push: bool = typer.Option(False, "--push", help="Also push onto the stack."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content only."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory (default: .code-clip/)."),
) -> None:
    """Copy code to a named clipboard. Reads from --file or stdin."""
    content, line_start, line_end = _read_stdin_or_file(file, lines, json_mode)
    if not content:
        err = ClipboardError("Content is empty", hint="Pipe code via stdin or use --file.")
        exit_with_error(err, json_mode=json_mode)

    op = build_copy_call(
        name,
        content,
        source_file=str(Path(file).resolve()) if file else None,
        line_start=line_start,
        line_end=line_end,
        language=language,
        tags=tags or [],
        overwrite=overwrite,
        push=push,
    )
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# cut
# ---------------------------------------------------------------------------

@app.command()
def cut(
    name: str = typer.Argument(..., help="Clipboard name."),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="Source file path."),
    lines: Optional[str] = typer.Option(None, "--lines", "-l", help="Line range, e.g. '10-25'."),
    language: Optional[str] = typer.Option(None, "--lang", help="Language identifier."),
    tags: Optional[List[str]] = typer.Option(None, "--tag", "-t", help="Tag(s) (repeatable)."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite if name already exists."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be cut without saving."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content only."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Save code and record removal intent (does not modify source file)."""
    content, line_start, line_end = _read_stdin_or_file(file, lines, json_mode)
    if not content:
        err = ClipboardError("Content is empty", hint="Pipe code via stdin or use --file.")
        exit_with_error(err, json_mode=json_mode)

    if dry_run:
        info: dict = {
            "name": name,
            "operation": "cut",
            "dry_run": True,
            "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
            "source_file": str(Path(file).resolve()) if file else None,
            "line_start": line_start,
            "line_end": line_end,
        }
        print_result(info, json_mode=json_mode, raw=raw)
        return

    op = build_cut_call(
        name,
        content,
        source_file=str(Path(file).resolve()) if file else None,
        line_start=line_start,
        line_end=line_end,
        language=language,
        tags=tags or [],
        overwrite=overwrite,
    )
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        # Augment result with removal descriptor for the agent
        if file and line_start:
            result["removal_descriptor"] = {
                "action": "delete_lines",
                "file": str(Path(file).resolve()),
                "line_start": line_start,
                "line_end": line_end,
                "note": "Remove these lines from the source file using your editor.",
            }
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# paste
# ---------------------------------------------------------------------------

@app.command()
def paste(
    name: str = typer.Argument(..., help="Clipboard name to paste from."),
    pop: bool = typer.Option(False, "--pop", help="Remove clipboard entry after pasting."),
    strip_indent: bool = typer.Option(False, "--strip-indent", help="Remove common leading whitespace."),
    indent: Optional[int] = typer.Option(None, "--indent", help="Re-indent content to N spaces."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON (with metadata)."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content only (default for pipes)."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Output clipboard content. Use --json for metadata, --raw for content only."""
    op = build_paste_call(name, pop=pop, strip_indent=strip_indent, indent=indent)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=False)


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@app.command(name="list")
def list_cmd(
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    language: Optional[str] = typer.Option(None, "--lang", help="Filter by language."),
    sort: str = typer.Option("created", "--sort", help="Sort field: created, name, language."),
    limit: int = typer.Option(50, "--limit", "-n", help="Maximum entries to show."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """List all clipboard entries."""
    op = build_list_call(tag=tag, language=language, sort=sort, limit=limit)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------

@app.command()
def show(
    name: str = typer.Argument(..., help="Clipboard name."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content only."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Show clipboard content and full metadata."""
    op = build_show_call(name)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

@app.command()
def delete(
    name: str = typer.Argument(..., help="Clipboard name to delete."),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Delete a clipboard entry."""
    if not force and sys.stdout.isatty():
        confirm = typer.confirm(f"Delete clipboard '{name}'?")
        if not confirm:
            raise typer.Exit(0)
    op = build_delete_call(name)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

@app.command()
def clear(
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Only clear entries with this tag."),
    force: bool = typer.Option(False, "--force", help="Skip confirmation prompt."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Remove all clipboard entries (or all with a given tag)."""
    if not force and sys.stdout.isatty():
        target = f"entries with tag '{tag}'" if tag else "all clipboard entries"
        confirm = typer.confirm(f"Clear {target}?")
        if not confirm:
            raise typer.Exit(0)
    op = build_clear_call(tag=tag)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query."),
    scope: str = typer.Option("all", "--in", help="Search scope: name, content, tag, all."),
    language: Optional[str] = typer.Option(None, "--lang", help="Filter by language."),
    limit: int = typer.Option(20, "--limit", "-n", help="Maximum results."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Search clipboard entries by name, content, or tag."""
    op = build_search_call(query, scope=scope, language=language, limit=limit)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

@app.command()
def diff(
    name1: str = typer.Argument(..., help="First clipboard name."),
    name2: str = typer.Argument(..., help="Second clipboard name."),
    context: int = typer.Option(3, "--context", "-C", help="Context lines in diff output."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw diff only."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Show unified diff between two clipboard entries."""
    op = build_diff_call(name1, name2, context_lines=context)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# verify
# ---------------------------------------------------------------------------

@app.command()
def verify(
    name: str = typer.Argument(..., help="Clipboard name to verify."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Verify clipboard content matches current source file at recorded lines."""
    op = build_verify_call(name)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
        if result.get("verified") is False:
            raise typer.Exit(1)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

@app.command()
def merge(
    target: str = typer.Argument(..., help="Name for the merged clipboard."),
    sources: List[str] = typer.Argument(..., help="Source clipboard names to merge."),
    separator: str = typer.Option("\n", "--separator", help="Separator between merged contents."),
    delete_sources: bool = typer.Option(False, "--delete-sources", help="Remove source entries after merge."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Combine multiple clipboard entries into one."""
    if not sources:
        typer.echo("Error: provide at least one source name.", err=True)
        raise typer.Exit(1)
    op = build_merge_call(target, list(sources), separator=separator, delete_sources=delete_sources)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@app.command(name="export")
def export_cmd(
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file path (stdout if omitted)."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Export all clipboard entries to a JSON file (or stdout)."""
    op = build_export_call(output_file=output)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        if output:
            print_result(result, json_mode=json_mode)
        else:
            # Always JSON when writing to stdout
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

@app.command(name="import")
def import_cmd(
    input_file: str = typer.Argument(..., help="JSON file created by `code-clip export`."),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing entries."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Import clipboard entries from a JSON export file."""
    op = build_import_call(input_file, overwrite=overwrite)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# stack push
# ---------------------------------------------------------------------------

@stack_app.command(name="push")
def stack_push(
    name: str = typer.Argument(..., help="Clipboard name to push onto the stack."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Push a clipboard entry onto the LIFO stack."""
    op = build_stack_push_call(name)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# stack pop
# ---------------------------------------------------------------------------

@stack_app.command(name="pop")
def stack_pop(
    peek: bool = typer.Option(False, "--peek", help="Show top entry without removing it."),
    name: Optional[str] = typer.Option(None, "--name", help="Rename the popped entry."),
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    raw: bool = typer.Option(False, "--raw", help="Output raw content only."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Pop (or peek) the top entry from the stack."""
    op = build_stack_pop_call(peek=peek, name=name)
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode, raw=raw)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# stack list
# ---------------------------------------------------------------------------

@stack_app.command(name="list")
def stack_list(
    json_mode: bool = typer.Option(False, "--json", help="Output structured JSON."),
    store_dir: Optional[str] = typer.Option(None, "--dir", "-d", help="Storage directory."),
) -> None:
    """Show all entries on the stack (top first)."""
    op = build_stack_list_call()
    try:
        store = _get_store(store_dir)
        result = store.execute(op)
        print_result(result, json_mode=json_mode)
    except ClipboardError as e:
        exit_with_error(e, json_mode=json_mode)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app()


if __name__ == "__main__":
    main()
