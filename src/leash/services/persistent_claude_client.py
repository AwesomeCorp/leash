"""Persistent Claude Code client using ACP (Agent Client Protocol).

Uses ``claude-agent-acp`` (npx @zed-industries/claude-agent-acp) as the ACP
server process.  Falls back to a one-shot ``ClaudeCliClient`` on failure.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

from leash.services.acp_client_base import AcpClientBase, _resolve_npx_package
from leash.services.claude_cli_client import ClaudeCliClient, parse_response
from leash.services.copilot_cli_client import _parse_text_heuristic

if TYPE_CHECKING:
    from leash.config import ConfigurationManager
    from leash.models.configuration import LlmConfig
    from leash.models.llm_response import LLMResponse
    from leash.services.terminal_output_service import TerminalOutputService

logger = logging.getLogger(__name__)

_ACP_PACKAGE = "@zed-industries/claude-agent-acp"


class PersistentClaudeClient(AcpClientBase):
    """Persistent Claude Code LLM client over ACP.

    Spawns ``npx @zed-industries/claude-agent-acp`` as a persistent subprocess
    and communicates using the Agent Client Protocol (JSON-RPC over stdio).
    Falls back to one-shot ``ClaudeCliClient`` on failure.

    On Windows, ``cmd /c npx.CMD`` hangs for persistent processes because it
    doesn't properly forward stdin/stdout pipes. When the package is already
    cached, we resolve the entry-point script and invoke ``node`` directly.
    """

    @property
    def _label(self) -> str:
        return "claude"

    def _get_command_and_args(self) -> tuple[str, list[str]]:
        if sys.platform == "win32":
            resolved = _resolve_npx_package(_ACP_PACKAGE)
            if resolved is not None:
                node_exe, script_path = resolved
                logger.info("Using direct node invocation: %s %s", node_exe, script_path)
                return (node_exe, [script_path])
            logger.debug("npx package %s not cached, falling back to npx", _ACP_PACKAGE)
        return ("npx", [_ACP_PACKAGE])

    def _parse_assistant_text(self, text: str) -> LLMResponse:
        # Try structured JSON first; fall back to keyword heuristics for
        # conversational responses (the ACP agent doesn't always output JSON)
        result = parse_response(text)
        if result.success:
            return result
        if text and text.strip():
            logger.debug("JSON parsing failed for ACP response, falling back to heuristics")
            return _parse_text_heuristic(text)
        return result

    def _create_fallback_client(self):
        return ClaudeCliClient(
            self._config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )
