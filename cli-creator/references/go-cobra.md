# Go + Cobra: Agent-Friendly CLI Reference

## go.mod

```
module github.com/yourorg/mycli

go 1.22

require (
    github.com/spf13/cobra v1.8.0
    github.com/spf13/viper v1.18.2
    github.com/mattn/go-isatty v0.0.20
)
```

## Directory Structure

```
mycli/
  go.mod
  main.go
  cmd/
    root.go          # Root command, persistent flags, command registration
    search.go        # Example subcommand
    list.go          # Example subcommand
  internal/
    buildcalls/      # Pure functions that build typed request structs
      search.go
      search_test.go
      list.go
      list_test.go
    output/
      output.go      # Structured output (JSON / human / raw)
    errors/
      errors.go      # StructuredError, hints, formatting
    connection/
      client.go      # http.Client wrapper with retry
```

`main.go` is minimal:

```go
package main

import "github.com/yourorg/mycli/cmd"

func main() {
    cmd.Execute()
}
```

## Root Command (cmd/root.go)

```go
package cmd

import (
    "fmt"
    "os"

    "github.com/spf13/cobra"
    "github.com/spf13/viper"
)

var rootCmd = &cobra.Command{
    Use:   "mycli",
    Short: "A short description of your CLI",
    PersistentPreRunE: func(cmd *cobra.Command, args []string) error {
        return initConfig()
    },
}

func init() {
    rootCmd.PersistentFlags().Bool("json", false, "Output as JSON")
    rootCmd.PersistentFlags().Bool("raw", false, "Output raw response body")
    rootCmd.PersistentFlags().BoolP("verbose", "v", false, "Verbose output")

    viper.BindPFlag("json", rootCmd.PersistentFlags().Lookup("json"))
    viper.BindPFlag("raw", rootCmd.PersistentFlags().Lookup("raw"))
    viper.BindPFlag("verbose", rootCmd.PersistentFlags().Lookup("verbose"))

    // Register subcommands
    rootCmd.AddCommand(searchCmd)
    rootCmd.AddCommand(listCmd)
}

func initConfig() error {
    viper.SetConfigName(".mycli")
    viper.SetConfigType("yaml")
    viper.AddConfigPath("$HOME")
    viper.AddConfigPath(".")
    viper.AutomaticEnv()

    if err := viper.ReadInConfig(); err != nil {
        if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
            return fmt.Errorf("reading config: %w", err)
        }
    }
    return nil
}

func Execute() {
    if err := rootCmd.Execute(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
```

## Output Layer (internal/output/output.go)

```go
package output

import (
    "encoding/json"
    "fmt"
    "io"
    "os"

    "github.com/mattn/go-isatty"
    "github.com/spf13/viper"
)

// PrintOutput writes data to stdout. Behavior depends on flags:
//   --json:  JSON with indentation
//   --raw:   raw string passthrough (no trailing newline added)
//   default: human-readable formatting via stringer
func PrintOutput(w io.Writer, data any, rawBody string) error {
    if viper.GetBool("json") {
        return printJSON(w, data)
    }
    if viper.GetBool("raw") {
        _, err := fmt.Fprint(w, rawBody)
        return err
    }
    return printHuman(w, data)
}

func printJSON(w io.Writer, data any) error {
    b, err := json.MarshalIndent(data, "", "  ")
    if err != nil {
        return fmt.Errorf("marshalling json: %w", err)
    }
    _, err = fmt.Fprintln(w, string(b))
    return err
}

func printHuman(w io.Writer, data any) error {
    if s, ok := data.(fmt.Stringer); ok {
        _, err := fmt.Fprintln(w, s.String())
        return err
    }
    // Fallback: print as JSON even in human mode
    return printJSON(w, data)
}

// IsTTY returns true when stdout is a terminal. Use this to decide
// whether to show spinners, color, or progress bars.
func IsTTY() bool {
    return isatty.IsTerminal(os.Stdout.Fd()) || isatty.IsCygwinTerminal(os.Stdout.Fd())
}
```

## Error Layer (internal/errors/errors.go)

```go
package errors

import (
    "fmt"
    "regexp"
    "strings"
)

// StructuredError carries a message, an exit code, and an optional hint.
type StructuredError struct {
    Message  string `json:"message"`
    Code     int    `json:"code"`
    Hint     string `json:"hint,omitempty"`
    Original error  `json:"-"`
}

func (e *StructuredError) Error() string {
    if e.Hint != "" {
        return fmt.Sprintf("%s\nhint: %s", e.Message, e.Hint)
    }
    return e.Message
}

func (e *StructuredError) Unwrap() error {
    return e.Original
}

// HintRule maps an error pattern to a suggestion shown to the user.
type HintRule struct {
    Pattern *regexp.Regexp
    Hint    string
}

var defaultHints = []HintRule{
    {regexp.MustCompile(`(?i)401|unauthorized`), "Check your API token with `mycli auth status`."},
    {regexp.MustCompile(`(?i)404|not found`), "Verify the resource name. Use `mycli list` to see available items."},
    {regexp.MustCompile(`(?i)timeout|deadline exceeded`), "The server may be slow. Retry with --timeout=60s."},
    {regexp.MustCompile(`(?i)connection refused`), "Is the server running? Check --endpoint."},
}

// FindHint scans the error message against known patterns.
func FindHint(msg string) string {
    for _, rule := range defaultHints {
        if rule.Pattern.MatchString(msg) {
            return rule.Hint
        }
    }
    return ""
}

// FormatError wraps a raw error into a StructuredError with a hint.
func FormatError(err error, code int) *StructuredError {
    msg := err.Error()
    return &StructuredError{
        Message:  msg,
        Code:     code,
        Hint:     FindHint(msg),
        Original: err,
    }
}

// Wrap is a shorthand for the common case: wrap with exit code 1.
func Wrap(err error) *StructuredError {
    return FormatError(err, 1)
}

// Annotate returns a StructuredError with a custom message prefix.
func Annotate(err error, prefix string) *StructuredError {
    se := FormatError(err, 1)
    se.Message = fmt.Sprintf("%s: %s", prefix, strings.TrimSpace(se.Message))
    return se
}
```

## Connection Layer (internal/connection/client.go)

```go
package connection

import (
    "fmt"
    "io"
    "net/http"
    "time"
)

type Client struct {
    HTTP       *http.Client
    BaseURL    string
    Token      string
    MaxRetries int
}

func New(baseURL, token string) *Client {
    return &Client{
        HTTP: &http.Client{
            Timeout: 30 * time.Second,
        },
        BaseURL:    baseURL,
        Token:      token,
        MaxRetries: 3,
    }
}

// Do executes an HTTP request with retries on 5xx or transport errors.
// Returns the response body bytes and the raw *http.Response.
func (c *Client) Do(req *http.Request) ([]byte, *http.Response, error) {
    req.Header.Set("Authorization", "Bearer "+c.Token)
    req.Header.Set("Accept", "application/json")

    var lastErr error
    for attempt := 0; attempt <= c.MaxRetries; attempt++ {
        if attempt > 0 {
            time.Sleep(time.Duration(attempt) * 500 * time.Millisecond)
        }

        resp, err := c.HTTP.Do(req)
        if err != nil {
            lastErr = fmt.Errorf("request failed: %w", err)
            continue
        }

        body, err := io.ReadAll(resp.Body)
        resp.Body.Close()
        if err != nil {
            lastErr = fmt.Errorf("reading body: %w", err)
            continue
        }

        if resp.StatusCode >= 500 {
            lastErr = fmt.Errorf("server error: %d", resp.StatusCode)
            continue
        }

        return body, resp, nil
    }
    return nil, nil, lastErr
}
```

## Build Call Pattern (internal/buildcalls/)

Build functions are **pure**: they accept typed parameters and return a typed
request struct. No side effects, no `interface{}`.

```go
// internal/buildcalls/search.go
package buildcalls

import (
    "fmt"
    "net/http"
    "net/url"
)

type SearchParams struct {
    Query   string
    Limit   int
    Offset  int
    SortBy  string
}

// BuildSearchRequest constructs an *http.Request from typed params.
// No network call happens here -- the caller uses connection.Client.Do().
func BuildSearchRequest(baseURL string, p SearchParams) (*http.Request, error) {
    u, err := url.Parse(baseURL + "/api/v1/search")
    if err != nil {
        return nil, fmt.Errorf("parsing url: %w", err)
    }

    q := u.Query()
    q.Set("q", p.Query)
    if p.Limit > 0 {
        q.Set("limit", fmt.Sprintf("%d", p.Limit))
    }
    if p.Offset > 0 {
        q.Set("offset", fmt.Sprintf("%d", p.Offset))
    }
    if p.SortBy != "" {
        q.Set("sort", p.SortBy)
    }
    u.RawQuery = q.Encode()

    return http.NewRequest(http.MethodGet, u.String(), nil)
}
```

## Subcommand Example (cmd/search.go)

```go
package cmd

import (
    "fmt"
    "os"

    "github.com/spf13/cobra"
    "github.com/spf13/viper"
    "github.com/yourorg/mycli/internal/buildcalls"
    "github.com/yourorg/mycli/internal/connection"
    myerrors "github.com/yourorg/mycli/internal/errors"
    "github.com/yourorg/mycli/internal/output"
)

var searchCmd = &cobra.Command{
    Use:   "search [query]",
    Short: "Search for items",
    Args:  cobra.ExactArgs(1),
    RunE:  runSearch,
}

func init() {
    searchCmd.Flags().Int("limit", 20, "Max results")
    searchCmd.Flags().String("sort", "", "Sort field")
}

func runSearch(cmd *cobra.Command, args []string) error {
    limit, _ := cmd.Flags().GetInt("limit")
    sortBy, _ := cmd.Flags().GetString("sort")

    params := buildcalls.SearchParams{
        Query:  args[0],
        Limit:  limit,
        SortBy: sortBy,
    }

    client := connection.New(viper.GetString("endpoint"), viper.GetString("token"))

    req, err := buildcalls.BuildSearchRequest(client.BaseURL, params)
    if err != nil {
        return myerrors.Annotate(err, "building search request")
    }

    body, resp, err := client.Do(req)
    if err != nil {
        return myerrors.Wrap(err)
    }
    if resp.StatusCode != 200 {
        return myerrors.FormatError(
            fmt.Errorf("unexpected status %d: %s", resp.StatusCode, string(body)),
            1,
        )
    }

    // Parse body into a typed result, then print.
    // (parsing omitted for brevity -- unmarshal into a SearchResult struct)
    return output.PrintOutput(os.Stdout, string(body), string(body))
}
```

## Testing (internal/buildcalls/search_test.go)

Build functions are easy to test because they are pure. Use table-driven tests.

```go
package buildcalls

import "testing"

func TestBuildSearchRequest(t *testing.T) {
    tests := []struct {
        name    string
        base    string
        params  SearchParams
        wantURL string
        wantErr bool
    }{
        {
            name:    "basic query",
            base:    "https://api.example.com",
            params:  SearchParams{Query: "hello"},
            wantURL: "https://api.example.com/api/v1/search?q=hello",
        },
        {
            name:    "with limit and sort",
            base:    "https://api.example.com",
            params:  SearchParams{Query: "hello", Limit: 5, SortBy: "name"},
            wantURL: "https://api.example.com/api/v1/search?limit=5&q=hello&sort=name",
        },
        {
            name:    "query with spaces",
            base:    "https://api.example.com",
            params:  SearchParams{Query: "hello world"},
            wantURL: "https://api.example.com/api/v1/search?q=hello+world",
        },
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            req, err := BuildSearchRequest(tt.base, tt.params)
            if (err != nil) != tt.wantErr {
                t.Fatalf("error = %v, wantErr %v", err, tt.wantErr)
            }
            if err != nil {
                return
            }
            if got := req.URL.String(); got != tt.wantURL {
                t.Errorf("URL = %q, want %q", got, tt.wantURL)
            }
            if req.Method != "GET" {
                t.Errorf("Method = %q, want GET", req.Method)
            }
        })
    }
}
```

## Key Principles

- **Flags over env vars for agent use.** Agents pass `--json --limit=5` more reliably than setting env vars. Viper still reads env as a fallback.
- **`--json` everywhere.** Every subcommand must respect `--json` for machine-readable output. Agents parse JSON; humans read the default.
- **Typed params, typed results.** No `map[string]interface{}`. Build functions take a named struct and return `*http.Request`. Response parsing uses concrete structs.
- **Errors carry hints.** When an agent sees `hint: Check your API token`, it can act on it without guessing.
- **Pure build functions.** Separating request construction from execution makes unit tests trivial and keeps the network boundary explicit.
- **Retry at the connection layer.** Subcommands never implement retry logic. The `Client.Do` wrapper handles transient 5xx failures.
