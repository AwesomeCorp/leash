"""LLM client provider: factory, registry, and caching."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Callable

import httpx

from leash.models.llm_response import LLMResponse
from leash.services.anthropic_api_client import AnthropicApiClient
from leash.services.claude_cli_client import ClaudeCliClient
from leash.services.copilot_cli_client import CopilotCliClient
from leash.services.generic_rest_client import GenericRestClient
from leash.services.persistent_claude_client import PersistentClaudeClient
from leash.services.persistent_claude_stream_client import PersistentClaudeStreamClient
from leash.services.persistent_copilot_client import PersistentCopilotClient

if TYPE_CHECKING:
    from leash.config import ConfigurationManager
    from leash.models.configuration import LlmConfig
    from leash.services.llm_client import LLMClient
    from leash.services.terminal_output_service import TerminalOutputService

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_MINUTES = 10
_CLEANUP_INTERVAL_SECONDS = 300  # 5 minutes


class _SessionClientEntry:
    """Tracks a per-session LLM client and its last-used timestamp."""

    __slots__ = ("client", "last_used")

    def __init__(self, client: LLMClient) -> None:
        self.client = client
        self.last_used: float = time.monotonic()

    def touch(self) -> None:
        self.last_used = time.monotonic()


class LLMClientProvider:
    """Runtime LLM provider registry and switcher.

    Maps provider names to factory functions. Reads config.llm.provider on each
    call and delegates to the matching client. Caches the active client and
    recreates it if the provider changes.

    For the "claude-persistent" provider, maintains per-session client instances
    so multiple Claude Code sessions can query the LLM in parallel.

    Implements the LLMClient protocol itself by delegating to the active client.
    """

    def __init__(
        self,
        config_manager: ConfigurationManager,
        http_client: httpx.AsyncClient | None = None,
        terminal_output: TerminalOutputService | None = None,
    ) -> None:
        if config_manager is None:
            raise ValueError("config_manager is required")
        self._config_manager = config_manager
        self._http_client = http_client
        self._terminal_output = terminal_output

        self._lock = asyncio.Lock()
        self._cached_client: LLMClient | None = None
        self._cached_provider: str | None = None
        self._cached_model: str | None = None

        self._session_lock = asyncio.Lock()
        self._session_clients: dict[str, _SessionClientEntry] = {}

        self._cleanup_task: asyncio.Task[None] | None = None

        self._factories: dict[str, Callable[[LlmConfig], LLMClient]] = {
            "anthropic-api": self._create_anthropic_api_client,
            "claude-cli": self._create_claude_cli_client,
            "claude-persistent": self._create_persistent_claude_client,
            "claude-stream": self._create_persistent_claude_stream_client,
            "copilot-cli": self._create_copilot_cli_client,
            "copilot-persistent": self._create_persistent_copilot_client,
            "generic-rest": self._create_generic_rest_client,
        }

    def _get_or_create_http_client(self) -> httpx.AsyncClient:
        """Get or create an httpx.AsyncClient."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(300.0))
        return self._http_client

    def _create_anthropic_api_client(self, _config: LlmConfig) -> LLMClient:
        return AnthropicApiClient(  # type: ignore[return-value]
            http_client=self._get_or_create_http_client(),
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_claude_cli_client(self, config: LlmConfig) -> LLMClient:
        return ClaudeCliClient(  # type: ignore[return-value]
            config=config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_persistent_claude_client(self, config: LlmConfig) -> LLMClient:
        return PersistentClaudeClient(  # type: ignore[return-value]
            config=config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_persistent_claude_stream_client(self, config: LlmConfig) -> LLMClient:
        return PersistentClaudeStreamClient(  # type: ignore[return-value]
            config=config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_copilot_cli_client(self, config: LlmConfig) -> LLMClient:
        return CopilotCliClient(  # type: ignore[return-value]
            config=config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_persistent_copilot_client(self, config: LlmConfig) -> LLMClient:
        return PersistentCopilotClient(  # type: ignore[return-value]
            config=config,
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    def _create_generic_rest_client(self, _config: LlmConfig) -> LLMClient:
        return GenericRestClient(  # type: ignore[return-value]
            http_client=self._get_or_create_http_client(),
            config_manager=self._config_manager,
            terminal_output=self._terminal_output,
        )

    async def query(self, prompt: str) -> LLMResponse:
        """Send a prompt to the currently configured LLM provider."""
        try:
            client = await self.get_client()
        except Exception as exc:
            logger.error("Failed to initialize LLM provider: %s", exc)
            return LLMResponse(
                success=False,
                safety_score=0,
                error=f"Failed to initialize LLM provider: {exc}",
                reasoning="LLM provider initialization failed",
            )
        return await client.query(prompt)

    async def get_client(self) -> LLMClient:
        """Return the LLM client for the currently configured provider.

        Lazily creates clients on first use and caches them.
        If the provider changes, the old client is disposed and a new one is created.
        """
        config = self._config_manager.get_configuration()
        provider = config.llm.provider or "anthropic-api"
        model = config.llm.model or ""

        async with self._lock:
            # Return cached client if provider and model haven't changed
            if (
                self._cached_client is not None
                and self._cached_provider == provider
                and self._cached_model == model
            ):
                return self._cached_client

            # Dispose old client if switching providers or model
            if self._cached_client is not None:
                logger.info(
                    "Recreating LLM client (provider: %s→%s, model: %s→%s)",
                    self._cached_provider, provider, self._cached_model, model,
                )
                await self._dispose_client(self._cached_client)
                self._cached_client = None
                self._cached_provider = None
                self._cached_model = None

            factory = self._factories.get(provider)
            if factory is None:
                logger.warning("Unknown LLM provider '%s', falling back to anthropic-api", provider)
                factory = self._factories["anthropic-api"]

            self._cached_client = factory(config.llm)
            self._cached_provider = provider
            self._cached_model = model
            logger.info("Initialized LLM provider: %s (model: %s)", provider, model or "default")

            # Start cleanup task if not running
            if self._cleanup_task is None or self._cleanup_task.done():
                self._cleanup_task = asyncio.create_task(self._periodic_cleanup())

            return self._cached_client

    async def get_client_for_session(self, session_id: str | None) -> LLMClient:
        """Return the shared LLM client.

        All sessions share a single persistent process to avoid spawning
        multiple concurrent ACP subprocesses that compete for API quota.
        Fresh ACP sessions are created per-query, so there is no context
        bleed between hook sessions.
        """
        return await self.get_client()

    async def _periodic_cleanup(self) -> None:
        """Periodically clean up idle session clients."""
        while True:
            await asyncio.sleep(_CLEANUP_INTERVAL_SECONDS)
            await self._cleanup_idle_sessions()

    async def _cleanup_idle_sessions(self) -> None:
        """Dispose session clients that have been idle for more than the timeout."""
        cutoff = time.monotonic() - (_IDLE_TIMEOUT_MINUTES * 60)
        to_remove: list[str] = []

        async with self._session_lock:
            for sid, entry in self._session_clients.items():
                if entry.last_used < cutoff:
                    to_remove.append(sid)

            for sid in to_remove:
                entry = self._session_clients.pop(sid, None)
                if entry is not None:
                    logger.info("Disposing idle per-session client for session %s", sid)
                    await self._dispose_client(entry.client)

    @staticmethod
    async def _dispose_client(client: LLMClient) -> None:
        """Dispose a client if it has a dispose method."""
        if hasattr(client, "dispose"):
            try:
                await client.dispose()  # type: ignore[attr-defined]
            except Exception as exc:
                logger.debug("Exception while disposing client: %s", exc)

    async def dispose(self) -> None:
        """Clean up all clients and the cleanup task."""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Dispose all session clients
        async with self._session_lock:
            for entry in self._session_clients.values():
                await self._dispose_client(entry.client)
            self._session_clients.clear()

        # Dispose cached client
        async with self._lock:
            if self._cached_client is not None:
                await self._dispose_client(self._cached_client)
                self._cached_client = None
                self._cached_provider = None
                self._cached_model = None

        # Close http client if we created it
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
