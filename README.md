# Leash

Observe and enforce Claude Code permission requests via LLM-based safety analysis. Web dashboard, curl-based hooks, session tracking, and multi-provider LLM support.

**Core flow:** Claude Code &rarr; `curl` hook &rarr; `POST /api/hooks/claude` &rarr; LLM safety analysis &rarr; approve/deny/passthrough &rarr; Claude-formatted JSON

**Default mode:** Observe-only. Hooks log events but return no decision (Claude asks user as normal). Enforcement can be toggled from the dashboard or via `--enforce`.

## One-liner Install & Run

```bash
# Run directly from GitHub (no install needed)
uvx --from git+https://github.com/AwesomeCorp/leash-py leash

# Install globally so you can just type 'leash'
uv tool install git+https://github.com/AwesomeCorp/leash-py
leash
```

## Quick Start

```bash
leash                    # Start (auto-installs hooks, opens browser)
leash --enforce          # Start in enforcement mode
leash --no-hooks         # Start without installing hooks
leash --port 8080        # Custom port (default: 5050)
leash --no-browser       # Don't open browser on startup
```

On startup: loads config &rarr; installs hooks &rarr; starts at `http://localhost:5050` &rarr; opens browser &rarr; on Ctrl+C removes hooks.

## From Source

```bash
git clone https://github.com/AwesomeCorp/leash-py.git
cd leash-py
uv sync --all-extras
uv run leash
```

## How It Works

### Hook Architecture (curl-based, zero dependencies)

On startup, Leash writes to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [{
      "matcher": "Bash",
      "hooks": [{ "type": "command", "command": "curl -sS -X POST \"http://localhost:5050/api/hooks/claude?event=PermissionRequest\" -H \"Content-Type: application/json\" -d @- # leash" }]
    }]
  }
}
```

The `# leash` comment is a marker for clean uninstall (only removes our hooks, not yours).

### Enforcement Modes

| Mode | Behavior |
|------|----------|
| **Observe** (default) | Logs events with LLM analysis, returns `{}` &mdash; Claude asks user as normal |
| **Approve-Only** | Auto-approves safe requests, falls through to user on anything uncertain |
| **Enforce** | Returns approve/deny based on LLM safety scoring |

Dashboard button cycles: Observe &rarr; Approve-Only &rarr; Enforce &rarr; Observe.

### LLM Providers

| Provider | Config `llm.provider` | Description |
|----------|----------------------|-------------|
| Anthropic API | `anthropic-api` | Direct HTTP to Anthropic (fastest) |
| Claude CLI | `claude-cli` | One-shot `claude` subprocess |
| Persistent Claude | `claude-persistent` | Persistent `claude` process with stream-json I/O |
| Copilot CLI | `copilot-cli` | GitHub Copilot CLI subprocess |
| Generic REST | `generic-rest` | Any REST LLM API (OpenAI, local, etc.) |

## Web Dashboard

| Page | URL | Features |
|------|-----|----------|
| Dashboard | `/` | Stats, charts, profiles, insights, hooks install/enforce toggles |
| Live Logs | `/logs.html` | 6 filters, incremental updates, export CSV/JSON |
| Sessions | `/session.html` | Session list, detail timeline, live refresh |
| Transcripts | `/transcripts.html` | SSE live stream, markdown, tool rendering |
| Prompt Editor | `/prompts.html` | Edit LLM prompt templates |
| Configuration | `/config.html` | Service config + hook handler management |
| Claude Settings | `/claude-settings.html` | JSON editor for `~/.claude/settings.json` |
| Copilot Settings | `/copilot-settings.html` | JSON editor for `~/.copilot/hooks/hooks.json` |

## API Endpoints (48 total)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/hooks/claude?event={type}` | Main hook endpoint |
| POST | `/api/hooks/copilot?event={type}` | Copilot hook endpoint |
| GET | `/api/hooks/status` | Hook & enforcement status |
| POST | `/api/hooks/enforce` | Toggle enforcement mode |
| POST | `/api/hooks/install` | Install hooks |
| POST | `/api/hooks/uninstall` | Remove hooks |
| GET/PUT | `/api/config` | Configuration CRUD |
| GET/PUT | `/api/claude-settings` | Claude settings editor |
| GET/PUT | `/api/copilot-settings` | Copilot settings editor |
| GET | `/api/dashboard/stats` | Dashboard statistics |
| GET | `/api/dashboard/sessions` | Active sessions list |
| GET | `/api/dashboard/activity` | Recent activity feed |
| GET | `/api/dashboard/trends` | Daily trend data |
| GET | `/api/logs` | Filtered logs |
| DELETE | `/api/logs` | Clear all logs |
| GET | `/api/logs/export/{format}` | Export logs (csv/json) |
| GET | `/api/sessions/{id}` | Session details |
| GET/PUT | `/api/prompts/{name}` | Prompt template CRUD |
| GET | `/api/claude-logs/projects` | Transcript projects |
| GET | `/api/claude-logs/transcript/{id}` | Transcript entries |
| GET | `/api/claude-logs/transcript/{id}/stream` | SSE transcript stream |
| GET | `/api/terminal/stream` | SSE terminal output |
| POST | `/api/debug/llm` | LLM replay/debug |
| GET | `/api/profile` | Permission profiles |
| POST | `/api/profile/switch` | Switch profile |
| GET | `/api/adaptivethreshold/stats` | Adaptive threshold stats |
| POST | `/api/adaptivethreshold/override` | Record override |
| GET | `/api/insights` | Smart suggestions |
| POST | `/api/quickactions/{action}` | Quick actions (lockdown/trust/reset) |
| GET | `/api/auditreport/{id}` | JSON audit report |
| GET | `/api/auditreport/{id}/html` | HTML audit report |
| GET | `/api/tray/status` | Tray service status |
| GET | `/health` | Health check |

## Configuration

Config auto-created at `~/.leash/config.json`:

```json
{
  "llm": { "provider": "claude-persistent", "model": "opus", "timeout": 15000 },
  "server": { "port": 5050, "host": "localhost" },
  "security": { "apiKey": null, "rateLimitPerMinute": 600 },
  "profiles": { "activeProfile": "moderate" },
  "enforcementMode": "observe",
  "tray": { "enabled": true }
}
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Uvicorn |
| Models | Pydantic v2 (camelCase aliases) |
| Async I/O | aiofiles |
| HTTP client | httpx |
| SSE | sse-starlette |
| File watching | watchfiles |
| Frontend | Vanilla HTML/CSS/JS (zero dependencies) |
| Testing | pytest + pytest-asyncio + pytest-mock |
| Package mgmt | uv + pyproject.toml + hatchling |

## Development

```bash
uv sync --all-extras        # Install all deps including dev
uv run pytest -v             # Run 186 tests
uv run ruff check src/ tests/  # Lint
uv run leash                 # Run from source
```

## Security

- ASGI middleware pipeline: Security Headers &rarr; Rate Limiting (600/min) &rarr; API Key Auth
- Input sanitization, path traversal protection
- LLM prompt injection defense
- CORS localhost-only
- Hook error safety: any error returns `{}` (no opinion)
