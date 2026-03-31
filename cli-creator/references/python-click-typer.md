# Python CLI -- Click / Typer Reference

This reference covers building an agent-friendly CLI in Python using **Typer**
(recommended) or **Click**. It implements the four Agent-First Principles from
the main SKILL.md.

---

## 1. Project Setup

Use a `pyproject.toml` with a `[project.scripts]` entry point so `pip install`
creates the executable automatically.

```toml
[project]
name = "mycli"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "typer>=0.9,<1",
    "click>=8,<9",
    "httpx>=0.27",
    "platformdirs>=4",
    "rich>=13",
    "tenacity>=8",
]

[project.scripts]
mycli = "mycli.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/mycli"]
```

Install in editable mode during development:

```bash
pip install -e ".[dev]"
```

---

## 2. Directory Structure

```
src/mycli/
├── __init__.py
├── cli.py            # Typer app definition + entry point
├── commands/         # One file per command group
│   ├── __init__.py
│   ├── search.py
│   ├── fetch.py
│   └── api.py        # Escape-hatch command
├── build_calls.py    # Pure functions: CLI args -> API params
├── connection.py     # with_connection context manager
├── output.py         # print_output with TTY detection
├── errors.py         # Structured errors + hint rules
└── auth.py           # Optional: token storage & refresh
```

Each layer has a single responsibility. Commands are thin -- they call a
`build_xxx_call()` pure function, pass the result through `with_connection`,
and hand the response to `print_output`.

---

## 3. CLI Entry Point (`cli.py`)

```python
"""CLI entry point -- Typer app with global options."""
from __future__ import annotations

import typer

from mycli.commands import api, fetch, search

# Global state passed via typer.Context
class GlobalOpts:
    json: bool = False
    raw: bool = False
    verbose: bool = False

app = typer.Typer(
    name="mycli",
    help="Agent-friendly CLI for MyService.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,  # We handle errors ourselves
)


@app.callback()
def main_callback(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
    raw: bool = typer.Option(False, "--raw", help="Raw upstream response"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging to stderr"),
) -> None:
    """Global options applied before any subcommand."""
    opts = GlobalOpts()
    opts.json = json_output
    opts.raw = raw
    opts.verbose = verbose
    ctx.obj = opts


# Register command groups
app.command(name="search")(search.search_cmd)
app.command(name="fetch")(fetch.fetch_cmd)
app.add_typer(api.api_app, name="api")


def main() -> None:
    """Installed entry point."""
    app()
```

---

## 4. Output Layer (`output.py`)

TTY detection drives the default format. `--json` and `--raw` override it.

```python
"""Output formatting with TTY detection."""
from __future__ import annotations

import json
import sys
from typing import Any


def print_output(
    data: Any,
    *,
    json_mode: bool = False,
    raw_mode: bool = False,
    raw_text: str | None = None,
) -> None:
    """Print data in the appropriate format.

    Priority: --raw > --json > TTY-detect.
    """
    if raw_mode and raw_text is not None:
        sys.stdout.write(raw_text)
        if not raw_text.endswith("\n"):
            sys.stdout.write("\n")
        return

    if json_mode or not sys.stdout.isatty():
        # Agents and pipes get clean JSON
        sys.stdout.write(json.dumps(data, indent=2, default=str) + "\n")
        return

    # Interactive terminal -- use rich for pretty output
    _print_pretty(data)


def _print_pretty(data: Any) -> None:
    """Rich-formatted output for interactive terminals."""
    try:
        from rich.console import Console
        from rich.json import JSON as RichJSON

        console = Console()
        if isinstance(data, (dict, list)):
            console.print(RichJSON(json.dumps(data, default=str)))
        else:
            console.print(data)
    except ImportError:
        # Fallback if rich is not installed
        print(json.dumps(data, indent=2, default=str))


def print_error(
    error: str,
    why: str | None = None,
    hint: str | None = None,
    *,
    json_mode: bool = False,
) -> None:
    """Print a structured error to stderr."""
    if json_mode:
        payload: dict[str, str] = {"error": error}
        if why:
            payload["why"] = why
        if hint:
            payload["hint"] = hint
        sys.stderr.write(json.dumps(payload, indent=2) + "\n")
        return

    sys.stderr.write(f"Error: {error}\n")
    if why:
        sys.stderr.write(f"Why:   {why}\n")
    if hint:
        sys.stderr.write(f"Hint:  {hint}\n")
```

---

## 5. Error Layer (`errors.py`)

A dataclass-based structured error system with regex-driven hint rules.

```python
"""Structured errors with pattern-matched hints."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StructuredError:
    """An error with machine-readable fields."""
    error: str
    why: str | None = None
    hint: str | None = None

    def to_dict(self) -> dict[str, str]:
        d: dict[str, str] = {"error": self.error}
        if self.why:
            d["why"] = self.why
        if self.hint:
            d["hint"] = self.hint
        return d


@dataclass(frozen=True)
class HintRule:
    """Maps an error pattern to a helpful hint."""
    pattern: str          # Regex matched against the error message
    hint: str             # Hint text (may contain {0}, {1}... for groups)
    why: str | None = None


# -- Hint rules: extend this list as users report common errors -----------

HINT_RULES: list[HintRule] = [
    HintRule(
        pattern=r"401|unauthorized|invalid.*token",
        hint='Run `mycli login` to refresh your credentials.',
        why="Your auth token is missing or expired.",
    ),
    HintRule(
        pattern=r"404|not found",
        hint='Run `mycli search "<name>"` to find the correct ID.',
        why="The requested resource does not exist.",
    ),
    HintRule(
        pattern=r"rate.?limit|429",
        hint="Wait a moment and retry, or pass --verbose to see retry timing.",
        why="The upstream API rate-limited this request.",
    ),
    HintRule(
        pattern=r"invalid.*id|bad.*uuid|malformed.*id",
        hint='IDs look like "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx". '
             'Run `mycli search "<name>"` to find it.',
        why="The provided ID is not in the expected format.",
    ),
]


def find_hint(error_message: str, rules: list[HintRule] | None = None) -> HintRule | None:
    """Return the first HintRule whose pattern matches the error message."""
    for rule in (rules or HINT_RULES):
        if re.search(rule.pattern, error_message, re.IGNORECASE):
            return rule
    return None


def format_error(
    raw_error: str | Exception,
    *,
    rules: list[HintRule] | None = None,
) -> StructuredError:
    """Build a StructuredError, auto-attaching hints when a rule matches."""
    message = str(raw_error)
    matched = find_hint(message, rules)
    return StructuredError(
        error=message,
        why=matched.why if matched else None,
        hint=matched.hint if matched else None,
    )


def exit_with_error(
    raw_error: str | Exception,
    *,
    json_mode: bool = False,
    code: int = 1,
) -> None:
    """Format an error, print it to stderr, and exit."""
    import json

    err = format_error(raw_error)
    if json_mode:
        sys.stderr.write(json.dumps(err.to_dict(), indent=2) + "\n")
    else:
        sys.stderr.write(f"Error: {err.error}\n")
        if err.why:
            sys.stderr.write(f"Why:   {err.why}\n")
        if err.hint:
            sys.stderr.write(f"Hint:  {err.hint}\n")
    raise SystemExit(code)
```

---

## 6. Connection Layer (`connection.py`)

An async context manager that handles lifecycle, retries, and auth injection.

```python
"""Connection lifecycle with retry logic."""
from __future__ import annotations

import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx


@asynccontextmanager
async def with_connection(
    base_url: str,
    *,
    token: str | None = None,
    max_retries: int = 3,
    timeout: float = 30.0,
    verbose: bool = False,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async context manager providing a configured HTTP client.

    Handles auth headers, timeouts, and automatic teardown.
    """
    headers: dict[str, str] = {"User-Agent": "mycli/0.1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(timeout),
    ) as client:
        yield client


async def call_api(
    client: httpx.AsyncClient,
    *,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
    max_retries: int = 3,
    verbose: bool = False,
) -> httpx.Response:
    """Execute an API call with retry logic.

    Retries on 429 (rate limit) and 5xx errors with exponential backoff.
    """
    import asyncio

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.request(
                method=method,
                url=path,
                json=body,
                params=params,
            )
            # Note: httpx.AsyncClient.request is a coroutine
            if not asyncio.iscoroutine(response):
                resp = response  # type: ignore[assignment]
            else:
                resp = await response

            if resp.status_code == 429 or resp.status_code >= 500:
                wait = 2 ** attempt
                if verbose:
                    sys.stderr.write(
                        f"[retry] {resp.status_code} -- waiting {wait}s "
                        f"(attempt {attempt + 1}/{max_retries})\n"
                    )
                await asyncio.sleep(wait)
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}",
                    request=resp.request,
                    response=resp,
                )
                continue

            resp.raise_for_status()
            return resp

        except httpx.TransportError as exc:
            wait = 2 ** attempt
            if verbose:
                sys.stderr.write(
                    f"[retry] Transport error -- waiting {wait}s "
                    f"(attempt {attempt + 1}/{max_retries})\n"
                )
            await asyncio.sleep(wait)
            last_exc = exc

    raise last_exc or RuntimeError("All retries exhausted")
```

### Alternative: tenacity-based retry

If you prefer `tenacity` for retry logic:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception(lambda e: _is_retryable(e)),
    reraise=True,
)
async def call_api_with_tenacity(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    **kwargs: Any,
) -> httpx.Response:
    resp = await client.request(method, path, **kwargs)
    if resp.status_code == 429 or resp.status_code >= 500:
        raise httpx.HTTPStatusError(
            str(resp.status_code), request=resp.request, response=resp
        )
    resp.raise_for_status()
    return resp

def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {429, 500, 502, 503, 504}
    return isinstance(exc, httpx.TransportError)
```

---

## 7. Command Pattern

Every command follows the same three-step wiring:
`build_xxx_call` (pure) -> `with_connection` + `call_api` -> `print_output`.

### `build_calls.py` -- Pure Functions

```python
"""Pure functions: CLI arguments -> API call parameters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiCall:
    """Describes an API call without executing it."""
    method: str
    path: str
    params: dict[str, Any] | None = None
    body: dict[str, Any] | None = None


def build_search_call(
    query: str,
    *,
    limit: int = 20,
    sort: str | None = None,
) -> ApiCall:
    params: dict[str, Any] = {"q": query, "page_size": limit}
    if sort:
        params["sort"] = sort
    return ApiCall(method="GET", path="/search", params=params)


def build_fetch_call(resource_id: str) -> ApiCall:
    return ApiCall(method="GET", path=f"/resources/{resource_id}")


def build_create_call(
    title: str,
    *,
    body: str | None = None,
    tags: list[str] | None = None,
) -> ApiCall:
    payload: dict[str, Any] = {"title": title}
    if body is not None:
        payload["body"] = body
    if tags:
        payload["tags"] = tags
    return ApiCall(method="POST", path="/resources", body=payload)
```

### `commands/search.py` -- Wiring a Command

```python
"""Search command -- wires build_search_call to the connection and output."""
from __future__ import annotations

import asyncio

import typer

from mycli.build_calls import build_search_call
from mycli.connection import call_api, with_connection
from mycli.errors import exit_with_error
from mycli.output import print_output


def search_cmd(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query string"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max results"),
    sort: str | None = typer.Option(None, "--sort", "-s", help="Sort field"),
) -> None:
    """Search for resources by query."""
    opts = ctx.obj
    asyncio.run(_search(query, limit=limit, sort=sort, opts=opts))


async def _search(
    query: str,
    *,
    limit: int,
    sort: str | None,
    opts: object,
) -> None:
    call = build_search_call(query, limit=limit, sort=sort)

    try:
        async with with_connection(
            "https://api.example.com",
            verbose=opts.verbose,  # type: ignore[attr-defined]
        ) as client:
            resp = await call_api(
                client,
                method=call.method,
                path=call.path,
                params=call.params,
                verbose=opts.verbose,  # type: ignore[attr-defined]
            )
    except Exception as exc:
        exit_with_error(exc, json_mode=opts.json)  # type: ignore[attr-defined]

    data = resp.json()
    print_output(
        data,
        json_mode=opts.json,  # type: ignore[attr-defined]
        raw_mode=opts.raw,    # type: ignore[attr-defined]
        raw_text=resp.text,
    )
```

---

## 8. Click vs Typer

Typer is built on top of Click. Choose based on your needs:

| | Typer | Click |
|---|---|---|
| Argument parsing | Type hints drive everything | Decorators define everything |
| Learning curve | Lower -- Pythonic, less boilerplate | Moderate -- explicit but verbose |
| Complex subgroups | Adequate for most CLIs | Better for deeply nested groups |
| Customization | Limited (delegates to Click) | Full control over parsing |
| Async support | Via `asyncio.run()` wrapper | Via `asyncio.run()` wrapper |

**Rule of thumb**: Start with Typer. Switch to Click only if you need custom
parameter types, deeply nested command groups, or non-standard parsing.

### Equivalent Patterns

#### Typer version

```python
import typer

app = typer.Typer()

@app.callback()
def main(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    ctx.obj = {"json": json_output, "verbose": verbose}

@app.command()
def search(
    ctx: typer.Context,
    query: str = typer.Argument(..., help="Search query"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Search for resources."""
    opts = ctx.obj
    print(f"Searching for {query!r}, limit={limit}, json={opts['json']}")

if __name__ == "__main__":
    app()
```

#### Click version

```python
import click

@click.group()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
@click.pass_context
def cli(ctx: click.Context, json_output: bool, verbose: bool) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    ctx.obj["verbose"] = verbose

@cli.command()
@click.argument("query")
@click.option("--limit", "-n", default=20, help="Max results")
@click.pass_context
def search(ctx: click.Context, query: str, limit: int) -> None:
    """Search for resources."""
    opts = ctx.obj
    click.echo(f"Searching for {query!r}, limit={limit}, json={opts['json']}")

if __name__ == "__main__":
    cli()
```

#### Click: Custom parameter type (not easily done in Typer)

```python
import click
import json as json_module

class JsonParam(click.ParamType):
    """Accept a JSON string or '-' for stdin."""
    name = "JSON"

    def convert(
        self, value: str, param: click.Parameter | None, ctx: click.Context | None
    ) -> dict:
        if value == "-":
            import sys
            value = sys.stdin.read()
        try:
            return json_module.loads(value)
        except json_module.JSONDecodeError as exc:
            self.fail(f"Invalid JSON: {exc}", param, ctx)

JSON = JsonParam()

@cli.command()
@click.argument("endpoint")
@click.argument("payload", type=JSON, default="{}")
@click.pass_context
def api(ctx: click.Context, endpoint: str, payload: dict) -> None:
    """Direct API access (escape hatch)."""
    click.echo(f"POST {endpoint} with {payload}")
```

Use this `JsonParam` type for the escape-hatch `api` command that accepts
arbitrary JSON payloads from arguments or piped stdin.
