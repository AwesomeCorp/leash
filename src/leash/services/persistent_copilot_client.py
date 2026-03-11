"""Persistent Copilot CLI client using ACP (Agent Client Protocol).

Uses ``copilot --acp`` as the ACP server process.  Falls back to a one-shot
``CopilotCliClient`` on failure.

Cross-platform: ACP uses standard stdin/stdout pipes which work on all
platforms (Mac, Linux, Windows).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from leash.services.acp_client_base import AcpClientBase
from leash.services.copilot_cli_client import CopilotCliClient, parse_text_response

if TYPE_CHECKING:
    from leash.config import ConfigurationManager
    from leash.models.configuration import LlmConfig
    from leash.models.llm_response import LLMResponse
    from leash.services.terminal_output_service import TerminalOutputService


class PersistentCopilotClient(AcpClientBase):
    """Persistent Copilot LLM client over ACP.

    Spawns ``copilot --acp`` (or ``gh copilot --acp``) as a persistent
    subprocess and communicates using the Agent Client Protocol (JSON-RPC
    over stdio).  Falls back to one-shot ``CopilotCliClient`` on failure.
    """

    @property
    def _label(self) -> str:
        return "copilot"

    def _get_command_and_args(self) -> tuple[str, list[str]]:
        cmd = None
        if self._config_manager is not None:
            try:
                cmd = self._config_manager.get_configuration().llm.command
            except Exception:
                pass
        if not cmd:
            cmd = self._config.command
        if not cmd:
            cmd = "copilot"

        acp_flags = ["--acp", "--no-custom-instructions", "--disable-builtin-mcps"]
        if cmd.lower() == "gh":
            return ("gh", ["copilot", *acp_flags])
        return (cmd, acp_flags)

    def _parse_assistant_text(self, text: str) -> LLMResponse:
        return parse_text_response(text)

    def _create_fallback_client(self):
        return CopilotCliClient(
            self._config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )
