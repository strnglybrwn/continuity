from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError
from sqlalchemy.orm import Session

from app.persistence.database import get_db_session
from app.services.heartbeat_service import (
    heartbeat_reminder_at,
    is_heartbeat_reminder_due,
    list_heartbeats,
    update_heartbeat_dashboard_settings,
)


router = APIRouter(
    prefix="/ui",
    tags=["heartbeat-dashboard"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
)


class HeartbeatDashboardUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    owner_email: EmailStr
    reminder_days: int = Field(ge=0, le=364)
    arm_reminder_now: bool = False


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
            "updated": request.query_params.get("updated"),
            "error": request.query_params.get("error"),
        },
    )


@router.post(
    "/heartbeats/{heartbeat_id}",
)
def update_heartbeat_dashboard(
    heartbeat_id: UUID,
    session: DatabaseSession,
    owner_email: str = Form(...),
    reminder_days: int = Form(...),
    arm_reminder_now: bool = Form(False),
) -> RedirectResponse:
    try:
        payload = HeartbeatDashboardUpdate(
            owner_email=owner_email,
            reminder_days=reminder_days,
            arm_reminder_now=arm_reminder_now,
        )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': message})}",
            status_code=303,
        )

    try:
        heartbeat = update_heartbeat_dashboard_settings(
            session,
            heartbeat_id,
            owner_email=str(payload.owner_email),
            reminder_days=payload.reminder_days,
            arm_reminder_now=payload.arm_reminder_now,
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
            status_code=303,
        )

    if heartbeat is None:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': 'Heartbeat not found'})}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/ui/heartbeats?{urlencode({'updated': str(heartbeat.id)})}",
        status_code=303,
    )
