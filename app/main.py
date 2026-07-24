import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.checkins import router as checkin_router
from app.api.heartbeat_dashboard import router as heartbeat_dashboard_router
from app.api.heartbeat_events import router as heartbeat_event_router
from app.api.heartbeats import router as heartbeat_router
from app.config import settings
from app.core.clock import utc_now
from app.scheduler import run_heartbeat_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    scheduler_task: asyncio.Task[None] | None = None

    if settings.heartbeat_scheduler_enabled:
        scheduler_task = asyncio.create_task(
            run_heartbeat_scheduler(
                settings.heartbeat_scheduler_interval_seconds,
            ),
            name="heartbeat-status-scheduler",
        )

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()

            with suppress(asyncio.CancelledError):
                await scheduler_task


app = FastAPI(
    title=settings.application_name,
    version=settings.application_version,
    lifespan=lifespan,
)

app.include_router(heartbeat_router)
app.include_router(heartbeat_event_router)
app.include_router(checkin_router)
app.include_router(heartbeat_dashboard_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "application": settings.application_name,
        "version": settings.application_version,
        "environment": settings.environment,
        "timestamp": utc_now().isoformat(),
    }
