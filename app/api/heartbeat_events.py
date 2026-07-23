from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatEventEvaluationResponse,
    HeartbeatEventDeliveredResponse,
    HeartbeatEventMetricsResponse,
    HeartbeatEventResponse,
    HeartbeatReminderNotificationResponse,
)
from app.config import settings
from app.persistence.database import get_db_session
from app.persistence.models import HeartbeatEvent
from app.services.heartbeat_event_service import (
    get_pending_heartbeat_event_metrics,
    list_pending_heartbeat_events,
    mark_heartbeat_event_delivered,
    prepare_reminder_notification,
    ReminderNotificationPreparationError,
)
from app.services.heartbeat_service import evaluate_due_heartbeats

router = APIRouter(
    prefix="/heartbeat-events",
    tags=["heartbeat-events"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


def _pending_event_response(
    event: HeartbeatEvent,
) -> HeartbeatEventResponse:
    return HeartbeatEventResponse(
        id=event.id,
        heartbeat_id=event.heartbeat_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        delivered_at=event.delivered_at,
        created_at=event.created_at,
        owner_name=event.heartbeat.owner_name,
        owner_email=event.heartbeat.owner_email,
    )


@router.get(
    "/pending",
    response_model=list[HeartbeatEventResponse],
)
def list_pending_heartbeat_events_endpoint(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[HeartbeatEventResponse]:
    events = list_pending_heartbeat_events(
        session,
        limit=limit,
    )

    return [_pending_event_response(event) for event in events]


@router.post(
    "/evaluate-due",
    response_model=HeartbeatEventEvaluationResponse,
)
def evaluate_due_heartbeat_events_endpoint(
    session: DatabaseSession,
) -> HeartbeatEventEvaluationResponse:
    result = evaluate_due_heartbeats(session)

    return HeartbeatEventEvaluationResponse(
        evaluated=result.evaluated,
        changed=result.changed,
    )


@router.get(
    "/metrics",
    response_model=HeartbeatEventMetricsResponse,
)
def heartbeat_event_metrics_endpoint(
    session: DatabaseSession,
    stale_after_seconds: Annotated[
        int, Query(gt=0, le=604800)
    ] = settings.heartbeat_pending_alert_seconds,
) -> HeartbeatEventMetricsResponse:
    metrics = get_pending_heartbeat_event_metrics(
        session,
        stale_after_seconds=stale_after_seconds,
    )

    return HeartbeatEventMetricsResponse(
        pending_total=metrics.pending_total,
        pending_reminder_due_total=metrics.pending_reminder_due_total,
        oldest_pending_occurred_at=metrics.oldest_pending_occurred_at,
        oldest_pending_age_seconds=metrics.oldest_pending_age_seconds,
        stale_pending_alert=metrics.stale_pending_alert,
        stale_reminder_due_total=metrics.stale_reminder_due_total,
        stale_after_seconds=stale_after_seconds,
    )


@router.post(
    "/{event_id}/prepare-reminder",
    response_model=HeartbeatReminderNotificationResponse,
)
def prepare_heartbeat_event_reminder_endpoint(
    event_id: UUID,
    session: DatabaseSession,
) -> HeartbeatReminderNotificationResponse:
    try:
        event, notification, checkin_url = prepare_reminder_notification(
            session,
            event_id,
            public_base_url=settings.public_base_url,
        )
    except ReminderNotificationPreparationError as exc:
        detail = str(exc)

        if detail == "Heartbeat event not found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=detail,
            ) from exc

        if detail == "Heartbeat event is already delivered":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
        ) from exc

    return HeartbeatReminderNotificationResponse(
        event_id=event.id,
        heartbeat_id=event.heartbeat_id,
        owner_name=notification.recipient.name,
        owner_email=notification.recipient.email,
        subject=notification.message.subject,
        text_body=notification.message.text_body,
        html_body=notification.message.html_body,
        checkin_url=checkin_url,
    )


@router.post(
    "/{event_id}/delivered",
    response_model=HeartbeatEventDeliveredResponse,
)
def mark_heartbeat_event_delivered_endpoint(
    event_id: UUID,
    session: DatabaseSession,
) -> HeartbeatEventDeliveredResponse:
    event = mark_heartbeat_event_delivered(
        session,
        event_id,
    )

    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Heartbeat event not found",
        )

    return HeartbeatEventDeliveredResponse.model_validate(event)
