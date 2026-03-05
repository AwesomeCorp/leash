"""Windows tray and notification services.

Uses pystray for the system tray icon and windows-toasts for rich toast
notifications with interactive approve/deny buttons.

Both libraries are optional — the module imports cleanly without them and
falls back gracefully.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from typing import Any

from leash.models.tray_models import NotificationInfo, TrayDecision

logger = logging.getLogger(__name__)

# --- Optional dependency: pystray + Pillow (tray icon) ---
try:
    import pystray
    from PIL import Image, ImageDraw

    HAS_PYSTRAY = True
except ImportError:
    HAS_PYSTRAY = False

# --- Optional dependency: windows-toasts (rich toast notifications) ---
try:
    from windows_toasts import (
        InteractableWindowsToaster,
        Toast,
        ToastActivatedEventArgs,
        ToastButton,
    )

    HAS_TOASTS = True
except ImportError:
    HAS_TOASTS = False


def _create_default_icon() -> Any:
    """Create a small blue circle icon with a white checkmark."""
    if not HAS_PYSTRAY:
        return None
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([1, 1, 14, 14], fill=(59, 130, 246, 255))
    draw.line([(4, 8), (7, 11), (12, 5)], fill="white", width=2)
    return img


class WindowsTrayService:
    """Windows system tray icon using pystray on a background thread.

    Requires ``pystray`` and ``Pillow`` optional dependencies.
    """

    def __init__(self, dashboard_url: str = "http://localhost:5050") -> None:
        self._dashboard_url = dashboard_url
        self._icon: Any | None = None
        self._thread: threading.Thread | None = None
        self._started = False
        self._disposed = False

    @property
    def is_available(self) -> bool:
        return HAS_PYSTRAY and self._started and not self._disposed and self._icon is not None

    async def start(self) -> None:
        if not HAS_PYSTRAY or self._started or self._disposed:
            return
        if sys.platform != "win32":
            return

        loop = asyncio.get_running_loop()
        ready = asyncio.Event()

        def _run_tray() -> None:
            try:
                image = _create_default_icon()
                menu = pystray.Menu(
                    pystray.MenuItem("Open Dashboard", self._open_dashboard),
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem("Exit", self._exit_tray),
                )
                self._icon = pystray.Icon("leash", image, "Leash", menu)
                self._started = True
                loop.call_soon_threadsafe(ready.set)
                self._icon.run()
            except Exception:
                logger.debug("Failed to start Windows tray icon", exc_info=True)
                loop.call_soon_threadsafe(ready.set)

        self._thread = threading.Thread(target=_run_tray, daemon=True, name="TrayIconThread")
        self._thread.start()
        await ready.wait()

    def update_status(self, status: str) -> None:
        if not self.is_available:
            return
        try:
            text = f"Leash - {status}"
            self._icon.title = text[:63] if len(text) > 63 else text
        except Exception:
            pass

    def _open_dashboard(self) -> None:
        import webbrowser

        try:
            webbrowser.open(self._dashboard_url)
        except Exception:
            pass

    def _exit_tray(self) -> None:
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass

    def stop(self) -> None:
        """Stop the tray icon and clean up."""
        if self._disposed:
            return
        self._disposed = True
        self._started = False
        self._exit_tray()
        # Wait briefly for the tray thread to finish
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None


class WindowsNotificationService:
    """Windows notification service using windows-toasts for rich notifications.

    Supports interactive approve/deny buttons via Windows toast notifications.
    Falls back to pystray balloon notifications if windows-toasts is unavailable.
    """

    def __init__(self, tray_service: WindowsTrayService) -> None:
        self._tray = tray_service
        self._toaster: Any | None = None
        if HAS_TOASTS:
            try:
                self._toaster = InteractableWindowsToaster("Leash")
            except Exception:
                logger.debug("Failed to create Windows toaster", exc_info=True)

    @property
    def supports_interactive(self) -> bool:
        return self._toaster is not None

    async def show_alert(self, info: NotificationInfo) -> None:
        """Show a passive toast notification."""
        if self._toaster is not None:
            try:
                toast = Toast([info.title[:200], info.body[:500]])
                self._toaster.show_toast(toast)
                return
            except Exception:
                logger.debug("Toast alert failed, trying pystray fallback", exc_info=True)

        # Fallback to pystray balloon
        if self._tray.is_available and self._tray._icon is not None:
            try:
                self._tray._icon.notify(
                    title=info.title[:63],
                    message=info.body[:255],
                )
            except Exception:
                logger.debug("Failed to show Windows notification", exc_info=True)

    async def show_interactive(self, info: NotificationInfo, timeout: float) -> TrayDecision | None:
        """Show a toast with Approve/Deny buttons and wait for user response."""
        if self._toaster is None:
            return None

        loop = asyncio.get_running_loop()
        result_future: asyncio.Future[TrayDecision | None] = loop.create_future()

        def _on_activated(event_args: ToastActivatedEventArgs) -> None:
            try:
                args = event_args.arguments
                if "action=approve" in args:
                    loop.call_soon_threadsafe(result_future.set_result, TrayDecision.APPROVE)
                elif "action=deny" in args:
                    loop.call_soon_threadsafe(result_future.set_result, TrayDecision.DENY)
                else:
                    # Clicked the toast body (not a button) — treat as no decision
                    loop.call_soon_threadsafe(result_future.set_result, None)
            except Exception:
                if not result_future.done():
                    loop.call_soon_threadsafe(result_future.set_result, None)

        def _on_dismissed(_: Any) -> None:
            if not result_future.done():
                loop.call_soon_threadsafe(result_future.set_result, None)

        def _on_failed(_: Any) -> None:
            if not result_future.done():
                loop.call_soon_threadsafe(result_future.set_result, None)

        try:
            tool_label = info.tool_name or "unknown tool"
            score_str = f"Score: {info.safety_score}" if info.safety_score is not None else ""
            body = info.reasoning or info.body
            if score_str:
                body = f"{score_str} — {body}"

            toast = Toast([f"Leash: {tool_label} requires approval", body[:500]])
            toast.AddAction(ToastButton("Approve", "action=approve"))
            toast.AddAction(ToastButton("Deny", "action=deny"))
            toast.on_activated = _on_activated
            toast.on_dismissed = _on_dismissed
            toast.on_failed = _on_failed

            self._toaster.show_toast(toast)

            return await asyncio.wait_for(result_future, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except Exception:
            logger.debug("Failed to show interactive Windows toast", exc_info=True)
            return None
