"""FastAPI application factory with lifespan, middleware, and auto-router discovery."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from leash.config import ConfigurationManager

logger = logging.getLogger(__name__)


def _find_static_dir() -> Path:
    """Locate the static files directory."""
    # 1. Check relative to package (development)
    pkg_dir = Path(__file__).resolve().parent
    candidates = [
        pkg_dir.parent.parent / "static",  # repo root: leash-py/static/
        Path.home() / ".local" / "share" / "leash" / "static",  # installed
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return candidates[0]  # fallback even if missing


def _find_prompts_dir() -> Path:
    """Locate the prompts directory."""
    pkg_dir = Path(__file__).resolve().parent
    candidates = [
        pkg_dir.parent.parent / "prompts",
        Path.home() / ".local" / "share" / "leash" / "prompts",
    ]
    for d in candidates:
        if d.is_dir():
            return d
    return candidates[0]


def _discover_routers(app: FastAPI) -> None:
    """Auto-discover and include all routers from leash.routes package."""
    import leash.routes as routes_pkg

    for module_info in pkgutil.iter_modules(routes_pkg.__path__):
        if module_info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"leash.routes.{module_info.name}")
            if hasattr(mod, "router"):
                app.include_router(mod.router)
                logger.debug("Registered router: leash.routes.%s", module_info.name)
        except Exception:
            logger.exception("Failed to load router module: leash.routes.%s", module_info.name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — initialize services on startup, clean up on shutdown."""
    config_path = getattr(app.state, "config_path", None)
    config_mgr = ConfigurationManager(config_path=config_path)
    config = await config_mgr.load()
    app.state.config_manager = config_mgr
    app.state.configuration = config
    app.state.prompts_dir = str(_find_prompts_dir())

    logger.info("Leash started — port %d, enforcement: %s",
                config.server.port, config.enforcement_mode or "observe")
    yield
    logger.info("Leash shutting down")


def create_app(config_path: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Leash",
        description="Observe and enforce Claude Code permission requests",
        version="0.1.0",
        lifespan=lifespan,
    )

    if config_path:
        app.state.config_path = config_path

    # Auto-discover and register route modules
    _discover_routers(app)

    # Mount static files (HTML dashboard)
    static_dir = _find_static_dir()
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return app
