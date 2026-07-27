from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, model_validator
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import HeartbeatCreate
from app.config import settings
from app.core.clock import utc_now
from app.domain.heartbeat import HeartbeatEventType
from app.persistence.database import get_db_session
from app.persistence.models import Heartbeat
from app.services.heartbeat_attachment_service import (
    AttachmentValidationError,
    add_heartbeat_attachments,
    delete_heartbeat_attachment,
    parse_uploads,
    sanitize_uploads,
)
from app.services.heartbeat_service import (
    create_heartbeat,
    delete_heartbeat,
    heartbeat_escalation_at,
    heartbeat_reminder_at,
    is_heartbeat_escalation_due,
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

    owner_name: str = Field(min_length=1, max_length=200)
    owner_email: EmailStr
    escalation_enabled: bool = False
    escalation_contact_name: str | None = Field(default=None, min_length=1, max_length=200)
    escalation_contact_email: EmailStr | None = None

    @model_validator(mode="after")
    def validate_reminder_less_than_interval(self) -> "HeartbeatDashboardUpdate":
        if self.escalation_enabled and not self.escalation_contact_name:
            raise ValueError("escalation_contact_name is required when escalation_enabled is true")

        if self.escalation_enabled and self.escalation_contact_email is None:
            raise ValueError("escalation_contact_email is required when escalation_enabled is true")
        return self


DASHBOARD_TIMEZONE = ZoneInfo(settings.dashboard_display_timezone)
DEFAULT_INTERVAL_DAYS = 30
DEFAULT_REMINDER_DAYS = 7
DEFAULT_ESCALATION_DELAY_DAYS = 1


def _format_dashboard_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"

    localized = value.astimezone(DASHBOARD_TIMEZONE)

    return localized.strftime("%d/%m/%Y %H:%M %Z")


def _format_dashboard_datetime_input(value: datetime) -> str:
    return value.astimezone(DASHBOARD_TIMEZONE).strftime("%Y-%m-%dT%H:%M")


def _parse_dashboard_datetime_input(*, raw_value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw_value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid date and time") from exc

    localized = parsed.replace(tzinfo=DASHBOARD_TIMEZONE)
    return localized.astimezone(UTC)


def _lifecycle_days_between(*, earlier: datetime, later: datetime, field_name: str) -> int:
    delta_seconds = int((later - earlier).total_seconds())

    if delta_seconds < 0:
        raise ValueError(f"{field_name} must be after the previous lifecycle stage")

    day_seconds = settings.effective_lifecycle_day_seconds
    if delta_seconds % day_seconds != 0:
        raise ValueError(
            f"{field_name} must align to whole lifecycle days of {day_seconds} seconds"
        )

    return delta_seconds // day_seconds


def _risk_label(
    *,
    status: str,
    reminder_due: bool,
    escalation_due: bool,
) -> str:
    if escalation_due:
        return "Escalating"

    if status == "overdue":
        return "Overdue"

    if reminder_due:
        return "Reminder window"

    return "On track"


def _next_actions(
    *,
    status: str,
    reminder_days: int,
    reminder_at: datetime,
    next_due_at: datetime,
    escalation_enabled: bool,
    escalation_at: datetime,
    pending_event_times: dict[HeartbeatEventType, datetime],
    now: datetime,
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []

    if pending_event_times:
        pending_action_map = [
            (HeartbeatEventType.REMINDER_DUE, "Send reminder to owner"),
            (HeartbeatEventType.OVERDUE, "Send overdue warning to owner"),
            (HeartbeatEventType.ESCALATION_DUE, "Send escalation notice to contact"),
        ]

        for event_type, label in pending_action_map:
            occurred_at = pending_event_times.get(event_type)
            if occurred_at is None:
                continue

            actions.append(
                {
                    "label": label,
                    "time": _format_dashboard_datetime(occurred_at),
                    "state": "pending" if occurred_at > now else "ready",
                }
            )

        if actions:
            return actions

    if status == "active" and reminder_days > 0:
        actions.append(
            {
                "label": "Send reminder to owner",
                "time": _format_dashboard_datetime(reminder_at),
                "state": "pending" if reminder_at > now else "ready",
            }
        )

    if status == "active":
        actions.append(
            {
                "label": "Send overdue warning to owner",
                "time": _format_dashboard_datetime(next_due_at),
                "state": "pending" if next_due_at > now else "ready",
            }
        )

    if escalation_enabled:
        actions.append(
            {
                "label": "Send escalation notice to contact",
                "time": _format_dashboard_datetime(escalation_at),
                "state": "pending" if escalation_at > now else "ready",
            }
        )

    if not actions:
        actions.append(
            {
                "label": "No queued actions",
                "time": "-",
                "state": "idle",
            }
        )

    return actions


def _lifecycle_event_times(
    heartbeat: Any,
    *,
    pending_only: bool,
) -> dict[HeartbeatEventType, datetime]:
    event_times: dict[HeartbeatEventType, datetime] = {}

    for event in heartbeat.events:
        if pending_only and event.delivered_at is not None:
            continue

        if event.event_type not in {
            HeartbeatEventType.REMINDER_DUE,
            HeartbeatEventType.OVERDUE,
            HeartbeatEventType.ESCALATION_DUE,
        }:
            continue

        previous = event_times.get(event.event_type)
        if previous is None:
            event_times[event.event_type] = event.occurred_at
            continue

        if pending_only:
            if event.occurred_at < previous:
                event_times[event.event_type] = event.occurred_at
        elif event.occurred_at > previous:
            event_times[event.event_type] = event.occurred_at

    return event_times


def _latest_delivered_lifecycle_event_times(
    heartbeat: Any,
    *,
    now: datetime,
) -> dict[HeartbeatEventType, datetime]:
    delivered_times: dict[HeartbeatEventType, datetime] = {}

    for event in heartbeat.events:
        if event.delivered_at is None:
            continue

        if event.occurred_at > now:
            continue

        if event.event_type not in {
            HeartbeatEventType.REMINDER_DUE,
            HeartbeatEventType.OVERDUE,
            HeartbeatEventType.ESCALATION_DUE,
        }:
            continue

        previous = delivered_times.get(event.event_type)
        if previous is None or event.occurred_at > previous:
            delivered_times[event.event_type] = event.occurred_at

    return delivered_times


@router.get(
    "/heartbeats",
    response_class=HTMLResponse,
)
def list_heartbeats_dashboard(
    request: Request,
    session: DatabaseSession,
) -> HTMLResponse:
    now = utc_now()
    heartbeats = list_heartbeats(session)
    rows: list[dict[str, Any]] = []

    for heartbeat in heartbeats:
        reminder_at = heartbeat_reminder_at(heartbeat)
        escalation_at = heartbeat_escalation_at(heartbeat)
        pending_event_times = _lifecycle_event_times(
            heartbeat,
            pending_only=True,
        )
        delivered_event_times = _latest_delivered_lifecycle_event_times(
            heartbeat,
            now=now,
        )

        reminder_timeline_at = pending_event_times.get(
            HeartbeatEventType.REMINDER_DUE,
            delivered_event_times.get(
                HeartbeatEventType.REMINDER_DUE,
                reminder_at,
            ),
        )
        overdue_timeline_at = pending_event_times.get(
            HeartbeatEventType.OVERDUE,
            delivered_event_times.get(
                HeartbeatEventType.OVERDUE,
                heartbeat.next_due_at,
            ),
        )
        escalation_timeline_at = pending_event_times.get(
            HeartbeatEventType.ESCALATION_DUE,
            delivered_event_times.get(
                HeartbeatEventType.ESCALATION_DUE,
                escalation_at,
            ),
        )
        reminder_due = is_heartbeat_reminder_due(heartbeat, now=now)
        escalation_due = is_heartbeat_escalation_due(heartbeat, now=now)

        rows.append(
            {
                "id": str(heartbeat.id),
                "owner_name": heartbeat.owner_name,
                "owner_email": heartbeat.owner_email,
                "status": heartbeat.status.value,
                "interval_days": heartbeat.interval_days,
                "reminder_days": heartbeat.reminder_days,
                "escalation_enabled": bool(heartbeat.escalation_enabled),
                "escalation_delay_days": heartbeat.escalation_delay_days or 1,
                "escalation_contact_name": heartbeat.escalation_contact_name,
                "escalation_contact_email": heartbeat.escalation_contact_email,
                "last_checkin_at": heartbeat.last_checkin_at,
                "next_due_at": heartbeat.next_due_at,
                "reminder_at_display": _format_dashboard_datetime(
                    reminder_timeline_at,
                ),
                "next_due_at_display": _format_dashboard_datetime(
                    overdue_timeline_at,
                ),
                "escalation_at_display": _format_dashboard_datetime(
                    escalation_timeline_at,
                ),
                "reminder_at": reminder_at,
                "reminder_at_input": _format_dashboard_datetime_input(reminder_timeline_at),
                "next_due_at_input": _format_dashboard_datetime_input(overdue_timeline_at),
                "escalation_at_input": _format_dashboard_datetime_input(escalation_timeline_at),
                "is_reminder_due": reminder_due,
                "is_escalation_due": escalation_due,
                "risk_label": _risk_label(
                    status=heartbeat.status.value,
                    reminder_due=reminder_due,
                    escalation_due=escalation_due,
                ),
                "next_actions": _next_actions(
                    status=heartbeat.status.value,
                    reminder_days=heartbeat.reminder_days,
                    reminder_at=reminder_timeline_at,
                    next_due_at=overdue_timeline_at,
                    escalation_enabled=bool(heartbeat.escalation_enabled),
                    escalation_at=escalation_timeline_at,
                    pending_event_times=pending_event_times,
                    now=now,
                ),
                "attachments": [
                    {
                        "id": str(attachment.id),
                        "filename": attachment.filename,
                        "content_type": attachment.content_type,
                        "size_bytes": attachment.size_bytes,
                    }
                    for attachment in heartbeat.attachments
                ],
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="heartbeat_dashboard.html",
        context={
            "rows": rows,
            "total": len(rows),
            "updated": request.query_params.get("updated"),
            "created": request.query_params.get("created"),
            "deleted": request.query_params.get("deleted"),
            "error": request.query_params.get("error"),
        },
    )


@router.post(
    "/heartbeats",
)
def create_heartbeat_dashboard(
    session: DatabaseSession,
    owner_name: str = Form(...),
    owner_email: str = Form(...),
    escalation_enabled: bool = Form(False),
    escalation_contact_name: str | None = Form(None),
    escalation_contact_email: str | None = Form(None),
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> RedirectResponse:
    escalation_contact_name_normalized = (
        escalation_contact_name.strip() if escalation_contact_name else None
    )
    escalation_contact_email_normalized = (
        escalation_contact_email.strip() if escalation_contact_email else None
    )

    try:
        payload = HeartbeatCreate(
            owner_name=owner_name,
            owner_email=owner_email,
            interval_days=DEFAULT_INTERVAL_DAYS,
            reminder_days=DEFAULT_REMINDER_DAYS,
            escalation_enabled=escalation_enabled,
            escalation_delay_days=DEFAULT_ESCALATION_DELAY_DAYS,
            escalation_contact_name=escalation_contact_name_normalized,
            escalation_contact_email=escalation_contact_email_normalized,
        )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': message})}",
            status_code=303,
        )

    cleaned_uploads = sanitize_uploads(attachments or [])

    try:
        parsed_uploads = parse_uploads(cleaned_uploads)
    except AttachmentValidationError as exc:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
            status_code=303,
        )

    heartbeat = create_heartbeat(session, payload)

    try:
        add_heartbeat_attachments(
            session,
            heartbeat.id,
            parsed_uploads,
        )
    except AttachmentValidationError as exc:
        deleted = delete_heartbeat(session, heartbeat.id)
        if not deleted:
            return RedirectResponse(
                url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
                status_code=303,
            )

        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/ui/heartbeats?{urlencode({'created': str(heartbeat.id)})}",
        status_code=303,
    )


@router.post(
    "/heartbeats/{heartbeat_id}/delete",
)
def delete_heartbeat_dashboard(
    heartbeat_id: UUID,
    session: DatabaseSession,
) -> RedirectResponse:
    deleted = delete_heartbeat(session, heartbeat_id)

    if not deleted:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': 'Heartbeat not found'})}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/ui/heartbeats?{urlencode({'deleted': str(heartbeat_id)})}",
        status_code=303,
    )


@router.post(
    "/heartbeats/{heartbeat_id}",
)
def update_heartbeat_dashboard(
    heartbeat_id: UUID,
    session: DatabaseSession,
    owner_name: str = Form(...),
    owner_email: str = Form(...),
    escalation_enabled: bool = Form(False),
    escalation_contact_name: str | None = Form(None),
    escalation_contact_email: str | None = Form(None),
    reminder_at: str = Form(...),
    overdue_at: str = Form(...),
    escalation_at: str = Form(...),
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> RedirectResponse:
    escalation_contact_name_normalized = (
        escalation_contact_name.strip() if escalation_contact_name else None
    )
    escalation_contact_email_normalized = (
        escalation_contact_email.strip() if escalation_contact_email else None
    )

    try:
        payload = HeartbeatDashboardUpdate(
            owner_name=owner_name,
            owner_email=owner_email,
            escalation_enabled=escalation_enabled,
            escalation_contact_name=escalation_contact_name_normalized,
            escalation_contact_email=escalation_contact_email_normalized,
        )
    except ValidationError as exc:
        message = exc.errors()[0]["msg"]
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': message})}",
            status_code=303,
        )

    heartbeat = session.get(Heartbeat, heartbeat_id)

    if heartbeat is None:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': 'Heartbeat not found'})}",
            status_code=303,
        )

    try:
        reminder_at_utc = _parse_dashboard_datetime_input(
            raw_value=reminder_at,
            field_name="Reminder time",
        )
        overdue_at_utc = _parse_dashboard_datetime_input(
            raw_value=overdue_at,
            field_name="Overdue time",
        )
        escalation_at_utc = _parse_dashboard_datetime_input(
            raw_value=escalation_at,
            field_name="Escalation time",
        )

        current_time = utc_now()
        base_time = (
            heartbeat.last_checkin_at
            if heartbeat.last_checkin_at is not None
            else heartbeat.created_at
        )

        interval_days = _lifecycle_days_between(
            earlier=base_time,
            later=overdue_at_utc,
            field_name="Overdue time",
        )
        if interval_days < 1:
            raise ValueError("Overdue time must be at least 1 lifecycle day after baseline")

        reminder_days = _lifecycle_days_between(
            earlier=reminder_at_utc,
            later=overdue_at_utc,
            field_name="Overdue time",
        )
        if reminder_days >= interval_days:
            raise ValueError("Reminder time must be before overdue time")

        escalation_delay_days = _lifecycle_days_between(
            earlier=overdue_at_utc,
            later=escalation_at_utc,
            field_name="Escalation time",
        )
        if escalation_delay_days < 1:
            raise ValueError("Escalation time must be at least 1 lifecycle day after overdue time")

    except ValueError as exc:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
            status_code=303,
        )

    try:
        heartbeat = update_heartbeat_dashboard_settings(
            session,
            heartbeat_id,
            owner_name=payload.owner_name,
            owner_email=str(payload.owner_email),
            interval_days=interval_days,
            reminder_days=reminder_days,
            escalation_enabled=payload.escalation_enabled,
            escalation_delay_days=escalation_delay_days,
            escalation_contact_name=payload.escalation_contact_name,
            escalation_contact_email=(
                str(payload.escalation_contact_email)
                if payload.escalation_contact_email is not None
                else None
            ),
            now=current_time,
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

    cleaned_uploads = sanitize_uploads(attachments or [])

    try:
        parsed_uploads = parse_uploads(cleaned_uploads)
        add_heartbeat_attachments(
            session,
            heartbeat.id,
            parsed_uploads,
        )
    except AttachmentValidationError as exc:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': str(exc)})}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/ui/heartbeats?{urlencode({'updated': str(heartbeat.id)})}",
        status_code=303,
    )


@router.post(
    "/heartbeats/{heartbeat_id}/attachments/{attachment_id}/delete",
)
def delete_heartbeat_attachment_dashboard(
    heartbeat_id: UUID,
    attachment_id: UUID,
    session: DatabaseSession,
) -> RedirectResponse:
    deleted = delete_heartbeat_attachment(
        session,
        heartbeat_id,
        attachment_id,
    )

    if not deleted:
        return RedirectResponse(
            url=f"/ui/heartbeats?{urlencode({'error': 'Attachment not found'})}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/ui/heartbeats?{urlencode({'updated': str(heartbeat_id)})}",
        status_code=303,
    )
