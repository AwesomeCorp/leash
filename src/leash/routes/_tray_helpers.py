"""Shared tray notification helpers for hook endpoints."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from fastapi.responses import JSONResponse

from leash.models.tray_models import NotificationInfo, NotificationLevel, TrayDecision

if TYPE_CHECKING:
    from leash.models.configuration import TrayConfig
    from leash.services.tray.base import NotificationService
    from leash.services.tray.pending_decision import PendingDecisionService

# Empty JSON = no opinion; the AI assistant asks the user as normal
_NO_OPINION = JSONResponse(content={})

logger = logging.getLogger(__name__)


async def try_interactive_tray_decision(
    notification_svc: NotificationService | None,
    pending_decision_svc: PendingDecisionService | None,
    tray_config: TrayConfig | None,
    tool_name: str | None,
    safety_score: int | None,
    reasoning: str | None,
    category: str | None,
    provider: str,
) -> TrayDecision | None:
    """Create a pending decision, attempt interactive notification, and await result.

    Falls back to a passive alert if interactive is unavailable, then waits for
    a response from the tray or web dashboard. Returns the user's decision or
    None on timeout / unavailability.
    """
    if pending_decision_svc is None:
        return None

    timeout = getattr(tray_config, "interactive_timeout_seconds", 10) if tray_config else 10

    info = NotificationInfo(
        title=f"Leash: {tool_name or 'unknown'} requires approval",
        body=reasoning or "Awaiting decision",
        tool_name=tool_name,
        safety_score=safety_score,
        reasoning=reasoning,
        category=category,
        provider=provider,
        level=NotificationLevel.WARNING,
    )

    try:
        decision_id, future = pending_decision_svc.create_pending(info, timeout)
    except Exception:
        logger.warning("Failed to create pending tray decision for %s", tool_name, exc_info=True)
        return None

    # Show interactive notification if the service supports it
    if notification_svc is not None and getattr(notification_svc, "supports_interactive", False):
        try:
            result = await notification_svc.show_interactive(info, timeout)
            if result is not None:
                pending_decision_svc.try_resolve(decision_id, result)
                return result
        except Exception:
            logger.warning(
                "Interactive notification failed for %s, falling back to pending decision",
                tool_name, exc_info=True,
            )

    # Show passive alert to notify the user a decision is pending
    if notification_svc is not None:
        try:
            await notification_svc.show_alert(info)
        except Exception:
            logger.debug("Failed to show passive alert for pending decision %s", decision_id)

    # Wait for the decision from web dashboard or other UI;
    # on cancellation or error, clean up the pending entry
    try:
        return await future
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pending_decision_svc.cancel(decision_id)
        return None
    except Exception:
        logger.warning("Error awaiting tray decision %s for %s", decision_id, tool_name, exc_info=True)
        pending_decision_svc.cancel(decision_id)
        return None


async def show_passive_notification(
    notification_svc: NotificationService | None,
    tool_name: str | None,
    safety_score: int | None,
    reasoning: str | None,
    category: str | None,
    provider: str,
    decision: str,
) -> None:
    """Show a passive (non-interactive) tray notification for a tool decision."""
    if notification_svc is None:
        return

    level = NotificationLevel.DANGER if decision == "denied" else NotificationLevel.INFO
    verb = "Denied" if decision == "denied" else "Observed"

    info = NotificationInfo(
        title=f"Leash: {tool_name or 'unknown'} {verb}",
        body=reasoning or f"Score: {safety_score}",
        tool_name=tool_name,
        safety_score=safety_score,
        reasoning=reasoning,
        category=category,
        provider=provider,
        level=level,
    )

    try:
        await notification_svc.show_alert(info)
    except Exception:
        logger.debug("Failed to show passive notification", exc_info=True)


async def make_tray_decision(
    mode: str,
    output: Any,
    harness_client: Any,
    event: str,
    tool_name: str,
    notification_svc: NotificationService | None,
    pending_decision_svc: PendingDecisionService | None,
    tray_config: TrayConfig | None,
    provider: str,
) -> JSONResponse:
    """Apply enforcement mode decision logic with tray integration.

    Handles observe, approve-only, and enforce modes with interactive tray
    decisions and passive notifications. Returns a JSONResponse.
    """
    tray_enabled = tray_config and getattr(tray_config, "enabled", False)
    interactive_enabled = tray_enabled and getattr(tray_config, "interactive_enabled", True)

    if mode == "observe":
        logger.debug(
            "Observe mode - analyzed %s (score=%s) but not enforcing",
            tool_name, getattr(output, "safety_score", "?"),
        )
        if tray_enabled:
            await show_passive_notification(
                notification_svc, tool_name,
                getattr(output, "safety_score", None),
                getattr(output, "reasoning", None),
                getattr(output, "category", None),
                provider, "observed",
            )
        return _NO_OPINION

    elif mode == "approve-only":
        if getattr(output, "auto_approve", False) and harness_client is not None:
            response = harness_client.format_response(event, output)
            return JSONResponse(content=response)

        # Try interactive tray decision
        if interactive_enabled:
            tray_result = await try_interactive_tray_decision(
                notification_svc, pending_decision_svc, tray_config,
                tool_name, getattr(output, "safety_score", None),
                getattr(output, "reasoning", None),
                getattr(output, "category", None), provider,
            )
            if tray_result is not None:
                if tray_result == TrayDecision.APPROVE and harness_client is not None:
                    output.auto_approve = True
                    response = harness_client.format_response(event, output)
                    return JSONResponse(content=response)
                elif tray_result == TrayDecision.DENY:
                    return _NO_OPINION

        # Not safe enough for auto-approve and no tray override; fall through to user
        logger.debug(
            "Approve-only mode - %s not safe enough (score=%s), falling through to user",
            tool_name, getattr(output, "safety_score", "?"),
        )
        return _NO_OPINION

    else:
        # enforce mode
        if getattr(output, "auto_approve", False) and harness_client is not None:
            response = harness_client.format_response(event, output)
            return JSONResponse(content=response)

        # Try interactive tray decision before denying
        if interactive_enabled:
            tray_result = await try_interactive_tray_decision(
                notification_svc, pending_decision_svc, tray_config,
                tool_name, getattr(output, "safety_score", None),
                getattr(output, "reasoning", None),
                getattr(output, "category", None), provider,
            )
            if tray_result is not None:
                if tray_result == TrayDecision.APPROVE and harness_client is not None:
                    output.auto_approve = True
                    response = harness_client.format_response(event, output)
                    return JSONResponse(content=response)
                # TrayDecision.DENY: fall through to hard deny via harness_client

        # Deny + passive notification
        if tray_enabled and getattr(tray_config, "alert_on_denied", True):
            await show_passive_notification(
                notification_svc, tool_name,
                getattr(output, "safety_score", None),
                getattr(output, "reasoning", None),
                getattr(output, "category", None),
                provider, "denied",
            )

        if harness_client is not None:
            response = harness_client.format_response(event, output)
            return JSONResponse(content=response)
        return _NO_OPINION
