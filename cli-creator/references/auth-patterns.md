# Authentication Patterns

How to implement authentication in agent-friendly CLIs. Read this when the
upstream service requires auth.

---

## Choosing an Auth Pattern

| Auth Type | When to Use | Complexity |
|---|---|---|
| **API Key** | Simple APIs, personal tokens | Low |
| **OAuth 2.0 + PKCE** | Workspace-wide access, multi-user | High |
| **None** | Public APIs, local tools | None |

Default to API key unless the upstream specifically requires OAuth.

---

## API Key Pattern

### Flow

1. User runs `mycli login` (or any command triggers it)
2. Prompt for API key (or read from `--api-key` flag / env var)
3. Store in OS-specific config directory
4. Inject into requests via `withConnection()`

### Token Storage

Use OS-specific config directories with restrictive permissions:

```typescript
// Node.js
import envPaths from "env-paths";
import fs from "fs/promises";
import path from "path";

const paths = envPaths("mycli");
const tokenPath = path.join(paths.config, "token.json");

async function saveToken(token: string): Promise<void> {
  await fs.mkdir(paths.config, { recursive: true });
  await fs.writeFile(tokenPath, JSON.stringify({ token }), { mode: 0o600 });
}

async function loadToken(): Promise<string | null> {
  try {
    const data = JSON.parse(await fs.readFile(tokenPath, "utf8"));
    return data.token;
  } catch {
    return null;
  }
}
```

```python
# Python
from platformdirs import user_config_dir
from pathlib import Path
import json, os

CONFIG_DIR = Path(user_config_dir("mycli"))
TOKEN_PATH = CONFIG_DIR / "token.json"

def save_token(token: str) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps({"token": token}))
    TOKEN_PATH.chmod(0o600)

def load_token() -> str | None:
    try:
        return json.loads(TOKEN_PATH.read_text())["token"]
    except (FileNotFoundError, KeyError):
        return None
```

### Storage locations by OS

| OS | Node.js (env-paths) | Python (platformdirs) |
|---|---|---|
| macOS | `~/Library/Preferences/mycli` | `~/Library/Application Support/mycli` |
| Linux | `~/.config/mycli` | `~/.config/mycli` |
| Windows | `%APPDATA%/mycli/Config` | `C:\Users\<user>\AppData\Local\mycli` |

### File permissions

Always set `0o600` (owner read/write only) on token files. This prevents
other users on shared systems from reading credentials.

### Environment variable fallback

Support `MYCLI_API_KEY` environment variable as an alternative to stored
tokens. Priority order:

1. `--api-key` flag (highest priority)
2. `MYCLI_API_KEY` environment variable
3. Stored token file
4. Prompt for login (interactive) or error (non-interactive)

```typescript
function resolveToken(opts: { apiKey?: string }): string | null {
  return opts.apiKey
    ?? process.env.MYCLI_API_KEY
    ?? loadTokenSync();
}
```

---

## OAuth 2.0 + PKCE Pattern

For services that use OAuth (like Notion, GitHub, Google), implement the
Authorization Code flow with PKCE (Proof Key for Code Exchange).

### Flow

1. User runs `mycli login`
2. CLI generates PKCE code verifier + challenge
3. CLI opens browser to authorization URL
4. User authorizes in browser
5. Browser redirects to `http://localhost:<port>/callback`
6. CLI exchanges authorization code for tokens
7. CLI stores access + refresh tokens

### Implementation

```typescript
import crypto from "crypto";
import http from "http";
import open from "open";

interface OAuthConfig {
  clientId: string;
  authUrl: string;
  tokenUrl: string;
  redirectPort: number;
  scopes: string[];
}

async function login(config: OAuthConfig): Promise<TokenPair> {
  // 1. Generate PKCE
  const verifier = crypto.randomBytes(32).toString("base64url");
  const challenge = crypto
    .createHash("sha256")
    .update(verifier)
    .digest("base64url");

  // 2. Build authorization URL
  const params = new URLSearchParams({
    client_id: config.clientId,
    response_type: "code",
    redirect_uri: `http://localhost:${config.redirectPort}/callback`,
    scope: config.scopes.join(" "),
    code_challenge: challenge,
    code_challenge_method: "S256",
    state: crypto.randomBytes(16).toString("hex"),
  });
  const authorizationUrl = `${config.authUrl}?${params}`;

  // 3. Start local server to receive callback
  const code = await new Promise<string>((resolve, reject) => {
    const server = http.createServer((req, res) => {
      const url = new URL(req.url!, `http://localhost:${config.redirectPort}`);
      const authCode = url.searchParams.get("code");
      if (authCode) {
        res.writeHead(200, { "Content-Type": "text/html" });
        res.end("<h1>Authenticated! You can close this tab.</h1>");
        server.close();
        resolve(authCode);
      } else {
        res.writeHead(400);
        res.end("Missing authorization code");
        server.close();
        reject(new Error("No authorization code received"));
      }
    });
    server.listen(config.redirectPort);
    server.on("error", reject);
  });

  // 4. Open browser
  await open(authorizationUrl);

  // 5. Exchange code for tokens
  const tokenResponse = await fetch(config.tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      client_id: config.clientId,
      code,
      redirect_uri: `http://localhost:${config.redirectPort}/callback`,
      code_verifier: verifier,
    }),
  });

  const tokens: TokenPair = await tokenResponse.json();
  await saveTokens(tokens);
  return tokens;
}
```

### Token Refresh

```typescript
interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_at: number; // Unix timestamp
}

async function getValidToken(config: OAuthConfig): Promise<string> {
  const tokens = await loadTokens();
  if (!tokens) throw new StructuredError("Not authenticated", {
    hint: "Run `mycli login` to authenticate.",
  });

  if (Date.now() / 1000 < tokens.expires_at - 60) {
    return tokens.access_token;
  }

  // Refresh
  const response = await fetch(config.tokenUrl, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "refresh_token",
      client_id: config.clientId,
      refresh_token: tokens.refresh_token,
    }),
  });

  const newTokens: TokenPair = await response.json();
  await saveTokens(newTokens);
  return newTokens.access_token;
}
```

---

## Auth Commands

### `login`

```bash
mycli login              # Interactive: opens browser (OAuth) or prompts for key
mycli login --api-key sk-xxx  # Non-interactive: store API key directly
```

### `logout`

```bash
mycli logout             # Remove stored tokens
```

### `whoami`

```bash
mycli whoami             # Show current user info (verifies token is valid)
mycli whoami --json      # { "user": "...", "email": "...", "workspace": "..." }
```

`whoami` is especially useful for agents -- it verifies auth is working before
attempting other operations.

---

## Auto-Auth

For better agent experience, trigger auth automatically when a command needs
it but no token is found:

```typescript
async function withAuth<T>(fn: (token: string) => Promise<T>): Promise<T> {
  const token = await resolveToken();
  if (!token) {
    if (process.stdout.isTTY) {
      console.error("Not authenticated. Starting login...");
      await login(config);
      return withAuth(fn);
    }
    throw new StructuredError("Not authenticated", {
      hint: "Run `mycli login` to authenticate.",
    });
  }
  return fn(token);
}
```

In non-interactive mode (pipes, agents), throw a structured error with a hint
instead of attempting interactive login.
