from datetime import UTC, datetime

from fastapi import FastAPI

from app.config import settings


app = FastAPI(
    title=settings.application_name,
    version=settings.application_version,
)


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "healthy",
        "application": settings.application_name,
        "version": settings.application_version,
        "environment": settings.environment,
        "timestamp": datetime.now(UTC).isoformat(),
    }
