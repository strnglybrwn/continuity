from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.persistence.database import get_db_session
from app.services.heartbeat_service import (
    heartbeat_reminder_at,
    is_heartbeat_reminder_due,
    list_heartbeats,
)


router = APIRouter(
    prefix="/ui",
    tags=["heartbeat-dashboard"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
)


@router.get(
    "/heartbeats",
    response_class=HTMLResponse,
)
def list_heartbeats_dashboard(
    request: Request,
    session: DatabaseSession,
) -> HTMLResponse:
    heartbeats = list_heartbeats(session)
    rows: list[dict[str, Any]] = []

    for heartbeat in heartbeats:
        rows.append(
            {
                "id": str(heartbeat.id),
                "owner_name": heartbeat.owner_name,
                "owner_email": heartbeat.owner_email,
                "status": heartbeat.status.value,
                "interval_days": heartbeat.interval_days,
                "reminder_days": heartbeat.reminder_days,
                "last_checkin_at": heartbeat.last_checkin_at,
                "next_due_at": heartbeat.next_due_at,
                "reminder_at": heartbeat_reminder_at(heartbeat),
                "is_reminder_due": is_heartbeat_reminder_due(heartbeat),
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="heartbeat_dashboard.html",
        context={
            "rows": rows,
            "total": len(rows),
        },
    )
