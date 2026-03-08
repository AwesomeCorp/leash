"""Persistent Claude Code client using ACP (Agent Client Protocol).

Uses ``claude-agent-acp`` (npx @zed-industries/claude-agent-acp) as the ACP
server process.  Falls back to a one-shot ``ClaudeCliClient`` on failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leash.services.acp_client_base import AcpClientBase
from leash.services.claude_cli_client import ClaudeCliClient, parse_response

if TYPE_CHECKING:
    from leash.config import ConfigurationManager
    from leash.models.configuration import LlmConfig
    from leash.models.llm_response import LLMResponse
    from leash.services.terminal_output_service import TerminalOutputService


class PersistentClaudeClient(AcpClientBase):
    """Persistent Claude Code LLM client over ACP.

    Spawns ``npx @zed-industries/claude-agent-acp`` as a persistent subprocess
    and communicates using the Agent Client Protocol (JSON-RPC over stdio).
    Falls back to one-shot ``ClaudeCliClient`` on failure.
    """

    @property
    def _label(self) -> str:
        return "claude"

    def _get_command_and_args(self) -> tuple[str, list[str]]:
        return ("npx", ["@zed-industries/claude-agent-acp"])

    def _parse_assistant_text(self, text: str) -> LLMResponse:
        return parse_response(text)

    def _create_fallback_client(self):
        return ClaudeCliClient(
            self._config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )
