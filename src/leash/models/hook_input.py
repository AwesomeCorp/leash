"""Hook input model - represents data sent by Claude Code hooks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel


class HookInput(BaseModel):
    """Data received from a Claude Code or Copilot hook via curl."""

    model_config = {"alias_generator": to_camel, "populate_by_name": True}

    hook_event_name: str = ""
    session_id: str = ""
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    cwd: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: str = "claude"
