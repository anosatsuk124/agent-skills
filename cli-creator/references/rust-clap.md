# Rust CLI with Clap (Derive) -- Agent-Friendly Reference

## Cargo.toml

```toml
[package]
name = "mycli"
version = "0.1.0"
edition = "2021"

[dependencies]
clap = { version = "4", features = ["derive"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
anyhow = "1"
thiserror = "2"
reqwest = { version = "0.12", features = ["json", "rustls-tls"], default-features = false }
tokio = { version = "1", features = ["rt-multi-thread", "macros"] }
dirs = "6"
regex = "1"
```

## Directory Structure

```
src/
  main.rs           # Entrypoint, parse args, dispatch subcommands
  cli.rs            # Clap derive structs and enums
  commands/
    mod.rs           # Re-exports
    list.rs          # Handler for `list` subcommand
    create.rs        # Handler for `create` subcommand
  build_calls.rs    # Pure functions that build typed request structs
  connection.rs     # reqwest client, retry logic
  output.rs         # Terminal-aware output formatting
  errors.rs         # Structured errors, hints
```

## CLI Definition (`cli.rs`)

```rust
use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "mycli", version, about = "An agent-friendly CLI")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Command,

    #[command(flatten)]
    pub global: GlobalArgs,
}

#[derive(clap::Args, Debug, Clone)]
pub struct GlobalArgs {
    /// Output as JSON (machine-readable)
    #[arg(long, global = true)]
    pub json: bool,

    /// Output raw response body without formatting
    #[arg(long, global = true)]
    pub raw: bool,

    /// Enable verbose/debug output
    #[arg(long, short, global = true)]
    pub verbose: bool,
}

#[derive(Subcommand, Debug)]
pub enum Command {
    /// List resources
    List {
        /// Filter by name prefix
        #[arg(long)]
        prefix: Option<String>,

        /// Maximum items to return
        #[arg(long, default_value_t = 50)]
        limit: u32,
    },
    /// Create a new resource
    Create {
        /// Name of the resource
        #[arg(long)]
        name: String,

        /// Optional tags (comma-separated)
        #[arg(long, value_delimiter = ',')]
        tags: Vec<String>,
    },
}
```

## Entrypoint (`main.rs`)

```rust
mod cli;
mod commands;
mod build_calls;
mod connection;
mod errors;
mod output;

use clap::Parser;
use cli::{Cli, Command};

#[tokio::main]
async fn main() {
    let cli = Cli::parse();
    let client = connection::build_client();

    let result = match &cli.command {
        Command::List { prefix, limit } => {
            commands::list::run(&client, prefix.as_deref(), *limit, &cli.global).await
        }
        Command::Create { name, tags } => {
            commands::create::run(&client, name, tags, &cli.global).await
        }
    };

    if let Err(e) = result {
        errors::format_error(&e, &cli.global);
        std::process::exit(1);
    }
}
```

## Output Layer (`output.rs`)

```rust
use crate::cli::GlobalArgs;
use serde::Serialize;
use std::io::{self, Write};

pub fn print_output<T: Serialize + std::fmt::Display>(
    value: &T,
    raw_body: Option<&str>,
    global: &GlobalArgs,
) {
    let stdout = io::stdout();
    let mut handle = stdout.lock();

    if global.json {
        // Machine-readable: always JSON, no decoration
        let json = serde_json::to_string(value).expect("serialize output");
        writeln!(handle, "{json}").ok();
    } else if global.raw {
        // Pass through the raw API response body
        if let Some(body) = raw_body {
            writeln!(handle, "{body}").ok();
        }
    } else if is_terminal() {
        // Human-friendly: formatted, colored if desired
        writeln!(handle, "{value}").ok();
    } else {
        // Piped to another process: JSON for composability
        let json = serde_json::to_string(value).expect("serialize output");
        writeln!(handle, "{json}").ok();
    }
}

fn is_terminal() -> bool {
    std::io::stdout().is_terminal()
}

// Convenience wrapper for list-style output
pub fn print_list<T: Serialize + std::fmt::Display>(
    items: &[T],
    global: &GlobalArgs,
) {
    if global.json {
        let json = serde_json::to_string(items).expect("serialize list");
        println!("{json}");
    } else {
        for item in items {
            println!("{item}");
        }
    }
}
```

## Error Layer (`errors.rs`)

```rust
use crate::cli::GlobalArgs;
use regex::Regex;
use serde::Serialize;
use thiserror::Error;

#[derive(Error, Debug)]
pub enum CliError {
    #[error("API error ({status}): {message}")]
    Api { status: u16, message: String },

    #[error("Authentication failed: {0}")]
    Auth(String),

    #[error("Resource not found: {0}")]
    NotFound(String),

    #[error("Network error: {0}")]
    Network(#[from] reqwest::Error),

    #[error("{0}")]
    Other(#[from] anyhow::Error),
}

#[derive(Serialize)]
struct ErrorOutput {
    error: String,
    hint: Option<String>,
}

pub struct HintRule {
    pub pattern: Regex,
    pub hint: &'static str,
}

pub fn default_hint_rules() -> Vec<HintRule> {
    vec![
        HintRule {
            pattern: Regex::new(r"(?i)401|unauthorized|authentication failed").unwrap(),
            hint: "Run `mycli auth login` or set MYCLI_TOKEN in your environment.",
        },
        HintRule {
            pattern: Regex::new(r"(?i)404|not found").unwrap(),
            hint: "Check the resource name with `mycli list`.",
        },
        HintRule {
            pattern: Regex::new(r"(?i)timeout|timed out").unwrap(),
            hint: "The server may be slow. Retry with --verbose to see timing.",
        },
        HintRule {
            pattern: Regex::new(r"(?i)connection refused").unwrap(),
            hint: "Is the service running? Check MYCLI_BASE_URL.",
        },
    ]
}

pub fn format_error(err: &CliError, global: &GlobalArgs) {
    let msg = err.to_string();
    let hint = find_hint(&msg);

    if global.json {
        let out = ErrorOutput {
            error: msg,
            hint: hint.map(String::from),
        };
        eprintln!("{}", serde_json::to_string(&out).unwrap());
    } else {
        eprintln!("Error: {msg}");
        if let Some(h) = hint {
            eprintln!("Hint: {h}");
        }
    }
}

fn find_hint(msg: &str) -> Option<&'static str> {
    default_hint_rules()
        .iter()
        .find(|rule| rule.pattern.is_match(msg))
        .map(|rule| rule.hint)
}
```

## Connection Layer (`connection.rs`)

```rust
use crate::errors::CliError;
use reqwest::{Client, Response, StatusCode};
use std::time::Duration;

pub fn build_client() -> Client {
    Client::builder()
        .timeout(Duration::from_secs(30))
        .user_agent(concat!("mycli/", env!("CARGO_PKG_VERSION")))
        .build()
        .expect("build HTTP client")
}

pub fn base_url() -> String {
    std::env::var("MYCLI_BASE_URL").unwrap_or_else(|_| "https://api.example.com".into())
}

pub fn auth_token() -> Result<String, CliError> {
    std::env::var("MYCLI_TOKEN")
        .or_else(|_| read_token_from_config())
        .map_err(|_| CliError::Auth("No token found".into()))
}

fn read_token_from_config() -> Result<String, std::env::VarError> {
    let path = dirs::config_dir()
        .map(|d| d.join("mycli").join("token"))
        .ok_or(std::env::VarError::NotPresent)?;
    std::fs::read_to_string(path).map_err(|_| std::env::VarError::NotPresent)
}

/// Execute a request with simple retry (up to 3 attempts for transient errors).
pub async fn send_with_retry(
    client: &Client,
    req: reqwest::RequestBuilder,
) -> Result<Response, CliError> {
    let mut last_err = None;

    for attempt in 0..3 {
        if attempt > 0 {
            tokio::time::sleep(Duration::from_millis(500 * 2_u64.pow(attempt))).await;
        }

        // Clone the builder for each attempt
        let resp = match req.try_clone().expect("cloneable request").send().await {
            Ok(r) => r,
            Err(e) if e.is_timeout() || e.is_connect() => {
                last_err = Some(e);
                continue;
            }
            Err(e) => return Err(e.into()),
        };

        match resp.status() {
            s if s.is_success() => return Ok(resp),
            StatusCode::TOO_MANY_REQUESTS | StatusCode::SERVICE_UNAVAILABLE => {
                last_err = Some(resp.error_for_status().unwrap_err());
                continue;
            }
            StatusCode::UNAUTHORIZED => {
                return Err(CliError::Auth("Token rejected by server".into()));
            }
            StatusCode::NOT_FOUND => {
                let body = resp.text().await.unwrap_or_default();
                return Err(CliError::NotFound(body));
            }
            status => {
                let body = resp.text().await.unwrap_or_default();
                return Err(CliError::Api {
                    status: status.as_u16(),
                    message: body,
                });
            }
        }
    }

    Err(last_err.map(CliError::from).unwrap_or_else(|| {
        CliError::Other(anyhow::anyhow!("request failed after retries"))
    }))
}
```

## Build Call Pattern (`build_calls.rs`)

Pure functions that construct request data without performing I/O. Easy to test.

```rust
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ListRequest {
    pub url: String,
    pub prefix: Option<String>,
    pub limit: u32,
}

#[derive(Debug, Serialize)]
pub struct CreateRequest {
    pub url: String,
    pub body: CreateBody,
}

#[derive(Debug, Serialize)]
pub struct CreateBody {
    pub name: String,
    pub tags: Vec<String>,
}

/// Build a ListRequest -- no I/O, no async, fully deterministic.
pub fn build_list(base_url: &str, prefix: Option<&str>, limit: u32) -> ListRequest {
    ListRequest {
        url: format!("{base_url}/v1/resources"),
        prefix: prefix.map(String::from),
        limit,
    }
}

pub fn build_create(base_url: &str, name: &str, tags: &[String]) -> CreateRequest {
    CreateRequest {
        url: format!("{base_url}/v1/resources"),
        body: CreateBody {
            name: name.to_owned(),
            tags: tags.to_vec(),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn list_request_defaults() {
        let req = build_list("https://api.example.com", None, 50);
        assert_eq!(req.url, "https://api.example.com/v1/resources");
        assert!(req.prefix.is_none());
        assert_eq!(req.limit, 50);
    }

    #[test]
    fn list_request_with_prefix() {
        let req = build_list("https://api.example.com", Some("prod-"), 10);
        assert_eq!(req.prefix.as_deref(), Some("prod-"));
        assert_eq!(req.limit, 10);
    }

    #[test]
    fn create_request_body() {
        let tags = vec!["env:prod".into(), "team:infra".into()];
        let req = build_create("https://api.example.com", "my-resource", &tags);
        assert_eq!(req.body.name, "my-resource");
        assert_eq!(req.body.tags.len(), 2);
    }

    #[test]
    fn create_request_serializes() {
        let req = build_create("https://localhost", "test", &[]);
        let json = serde_json::to_value(&req.body).unwrap();
        assert_eq!(json["name"], "test");
        assert!(json["tags"].as_array().unwrap().is_empty());
    }
}
```

## Key Design Principles

1. **`--json` everywhere** -- every command supports `--json` for agent consumption.
2. **Pipe detection** -- non-terminal stdout defaults to JSON automatically.
3. **Structured errors with hints** -- regex-matched hints guide the user (or agent) to a fix.
4. **Pure build functions** -- request construction is separated from execution; tests run without a tokio runtime or network.
5. **Retry with backoff** -- transient failures (429, 503, timeouts) retry automatically.
6. **Config via env + file** -- `MYCLI_TOKEN` / `MYCLI_BASE_URL` env vars, falling back to `dirs::config_dir()`.
