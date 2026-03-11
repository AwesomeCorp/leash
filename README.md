# Leash

Observe and enforce Claude Code & Copilot CLI permission requests via LLM-based safety analysis. Web dashboard, system tray notifications, transcript browsing with token usage tracking, and multi-provider LLM support.

**Core flow:** Claude Code / Copilot CLI &rarr; `curl` hook &rarr; `POST /api/hooks/{client}` &rarr; LLM safety analysis &rarr; approve/deny/passthrough

**Default mode:** Observe-only. Hooks log events but return no decision. Enforcement can be toggled from the dashboard or via `--enforce`.

## Install & Run

### One-liner (any platform)

```bash
# Run directly from GitHub (no install needed)
uvx --from git+https://github.com/AwesomeCorp/leash leash

# Or install globally
uv tool install git+https://github.com/AwesomeCorp/leash
leash
```

On the first interactive launch, Leash opens a small console installer so you can pick a security profile and enforcement mode before it installs hooks and starts.

### pip install

```bash
pip install git+https://github.com/AwesomeCorp/leash.git
leash
```

### Platform-specific with tray support

**Windows** (tray icon + toast notifications with approve/deny buttons):
```powershell
pip install "leash[tray] @ git+https://github.com/AwesomeCorp/leash.git"
leash
```

**macOS**:
```bash
pip install "leash[tray] @ git+https://github.com/AwesomeCorp/leash.git"
leash
```

**Linux**:
```bash
pip install "leash[tray] @ git+https://github.com/AwesomeCorp/leash.git"
leash
# Optional: install notify-send and zenity for native notifications
```

### From source

```bash
git clone https://github.com/AwesomeCorp/leash.git
cd leash
uv sync --all-extras
uv run leash
```

### From release binary (no Python required)

Download the latest release for your platform from [Releases](https://github.com/AwesomeCorp/leash/releases):

| Platform | Download |
|----------|----------|
| Windows | `leash-windows-amd64.zip` |
| macOS (Intel) | `leash-macos-amd64.tar.gz` |
| macOS (Apple Silicon) | `leash-macos-arm64.tar.gz` |
| Linux | `leash-linux-amd64.tar.gz` |

Extract and run:
```bash
# Windows
.\leash.exe

# macOS / Linux
chmod +x leash
./leash
```

## Quick Start

```bash
leash                    # First interactive run shows setup, installs hooks, and records auto-start metadata
leash --enforce          # Start in enforcement mode
leash --no-hooks         # Start without installing hooks
leash --port 8080        # Custom port (default: 5050)
leash --no-browser       # Don't open browser on startup
```

On the first interactive startup, Leash saves the selected security profile and enforcement mode, records how it was launched, and installs Claude hooks. After that, SessionStart hooks can bring Leash back up automatically on later Claude/Copilot sessions if they are configured and Leash is not already running, and Claude SessionStart shows a message that protection is active. Settings (enforcement mode, security profile, LLM analysis toggle) persist across sessions.

## How It Works

### Hook Architecture (curl-based, zero dependencies)

On startup, Leash writes to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash|Edit|Write",
      "hooks": [{ "type": "command", "command": "curl -sS -X POST \"http://localhost:5050/api/hooks/claude?event=PreToolUse\" -H \"Content-Type: application/json\" -d @- # leash" }]
    }]
  }
}
```

The `# leash` comment is a marker for clean uninstall (only removes our hooks, not yours).

Leash also installs a SessionStart hook. It checks the configured local port, starts Leash in the background when needed, waits for `/health`, and then forwards the original session-start payload so Claude can display the protection-on message.

### Enforcement Modes

| Mode | Safe requests | Unsafe requests | Tray behavior | Timeout |
|------|--------------|----------------|---------------|---------|
| **Observe** (default) | No opinion (`{}`) | No opinion (`{}`) | Informational alerts (no buttons) | N/A |
| **Approve-Only** | Auto-approve | No opinion (`{}`) | Interactive (Approve/Deny/Ignore) | No opinion |
| **Enforce** | Auto-approve | **Deny** | Interactive (user can override) | Deny |

Dashboard button cycles: Observe &rarr; Approve-Only &rarr; Enforce &rarr; Observe.

- **Observe**: Logs events, optionally runs LLM analysis, but never returns a decision. Tray shows informational-only alerts. LLM analysis can be toggled on/off from the dashboard (off = pure log-only with zero latency).
- **Approve-only**: Auto-approves safe requests (score &ge; threshold). Unsafe requests return no opinion &mdash; Claude asks the user as normal. If tray is enabled, shows interactive Approve/Deny dialog for unsafe requests.
- **Enforce**: Full control. Auto-approves safe, denies unsafe by default. If tray is enabled, shows interactive dialog so the user can override the deny. On timeout, the deny executes.

### Auto-Start

Leash can auto-start when Claude Code or Copilot begins a session. Toggle the play button (&9205;) in the dashboard header to install/uninstall the SessionStart hook independently of other hooks.

### LLM Providers

| Provider | Config `llm.provider` | Description |
|----------|----------------------|-------------|
| Anthropic API | `anthropic-api` | Direct HTTP to Anthropic (fastest) |
| Claude CLI | `claude-cli` | One-shot `claude` subprocess |
| Claude Persistent (ACP) | `claude-persistent` | Persistent process via Agent Client Protocol |
| Claude Stream | `claude-stream` | Persistent process via `--output-format stream-json` |
| Copilot CLI | `copilot-cli` | GitHub Copilot CLI subprocess |
| Copilot Persistent (ACP) | `copilot-persistent` | Persistent process via ACP |
| Generic REST | `generic-rest` | Any REST LLM API (OpenAI, local, etc.) |

Persistent providers (`claude-persistent`, `claude-stream`, `copilot-persistent`) reuse sessions across queries, eliminating per-query session overhead. The provider is automatically recreated when the model config changes. If the model field is empty, the CLI uses its built-in default.

### System Tray & Notifications

Tray notifications work in all three enforcement modes:
- **Observe**: Informational alerts only (no buttons)
- **Approve-only**: Interactive Approve/Deny/Ignore for unsafe requests
- **Enforce**: Interactive dialog showing system deny, user can override

Platform support:
- **Windows**: System tray icon (pystray) + toast/popup notifications with interactive Approve/Deny/Ignore buttons
- **macOS**: Native notifications via osascript with Approve/Deny dialogs
- **Linux**: notify-send for alerts, zenity for interactive Approve/Deny dialogs

Install with `pip install "leash[tray]"` to enable.

## Web Dashboard

| Page | URL | Features |
|------|-----|----------|
| Dashboard | `/` | Stats, charts, profiles, insights, hooks install/enforce toggles |
| Live Logs | `/logs.html` | 6 filters, incremental updates, export CSV/JSON, link to transcripts |
| Transcripts | `/transcripts.html` | Hierarchical session tree (parent + subagents), token usage per session/project, SSE live stream, markdown rendering, tool diffs |
| Prompt Editor | `/prompts.html` | Edit LLM prompt templates |
| Configuration | `/config.html` | Service config + hook handler management |
| Claude Settings | `/claude-settings.html` | JSON editor for `~/.claude/settings.json` |
| Copilot Settings | `/copilot-settings.html` | JSON editor for `~/.copilot/hooks/hooks.json` |

### Transcript Features

- **Hierarchical sessions**: Parent sessions with expandable subagent children (Claude Code Agent tool)
- **Token usage tracking**: Per-session and per-project token counts with model breakdown (Claude + Copilot)
- **CWD from JSONL**: Project grouping uses actual working directory from transcript metadata
- **Live streaming**: SSE-based real-time transcript updates
- **Rich rendering**: Markdown, side-by-side diffs for Edit/Write tools, collapsible tool results

## Configuration

Config auto-created at `~/.leash/config.json`. All settings persist across sessions:

```json
{
  "llm": { "provider": "claude-persistent", "model": "opus", "timeout": 30000 },
  "server": { "port": 5050, "host": "localhost" },
  "security": { "apiKey": null, "rateLimitPerMinute": 600 },
  "profiles": { "activeProfile": "moderate" },
  "enforcementMode": "observe",
  "analyzeInObserveMode": true,
  "tray": {
    "enabled": true,
    "showInObserve": true,
    "showInApproveOnly": true,
    "interactiveTimeoutSeconds": 10,
    "sound": false,
    "useLargePopup": true
  }
}
```

## Development

```bash
uv sync --all-extras        # Install all deps including dev
uv run pytest -v            # Run tests
uv run ruff check src/ tests/  # Lint
uv run leash               # Run from source
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Web framework | FastAPI + Uvicorn |
| Models | Pydantic v2 (camelCase aliases) |
| HTTP client | httpx |
| SSE | sse-starlette |
| File watching | watchfiles |
| Tray (optional) | pystray + Pillow + windows-toasts |
| Frontend | Vanilla HTML/CSS/JS (zero dependencies) |
| Testing | pytest + pytest-asyncio + pytest-mock |
| Package mgmt | uv + pyproject.toml + hatchling |
| CI/CD | GitHub Actions (test + release) |

## Security

- ASGI middleware pipeline: Security Headers &rarr; Rate Limiting (600/min) &rarr; API Key Auth
- Input sanitization, path traversal protection
- LLM prompt injection defense
- CORS localhost-only
- Hook error safety: any error returns `{}` (no opinion)

## License

MIT
