"""Health check and shutdown endpoints."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from leash import __version__

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
@router.get("/api/health")
async def get_health() -> JSONResponse:
    """Return service health status."""
    return JSONResponse(
        content={
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": __version__,
        }
    )


@router.post("/api/shutdown")
async def shutdown() -> JSONResponse:
    """Initiate graceful server shutdown.

    Schedules SIGINT after a short delay so the HTTP response can be
    sent back to the client before the process begins shutting down.
    """
    logger.info("Shutdown requested via API")

    loop = asyncio.get_running_loop()
    loop.call_later(0.5, os.kill, os.getpid(), signal.SIGINT)

    return JSONResponse(content={"status": "shutting_down"})
