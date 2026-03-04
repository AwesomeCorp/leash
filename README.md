# Leash

Observe and enforce Claude Code permission requests via LLM-based safety analysis.

## Quick Start

```bash
# Install and run
uvx leash

# Or from source
uv run leash

# With enforcement enabled
uv run leash --enforce

# Skip hook installation
uv run leash --no-hooks
```

## Development

```bash
uv sync --all-extras
uv run pytest
uv run ruff check src/ tests/
```
