from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatEventDeliveredResponse,
    HeartbeatEventResponse,
)
from app.persistence.database import get_db_session
from app.persistence.models import HeartbeatEvent
from app.services.heartbeat_event_service import (
    list_pending_heartbeat_events,
    mark_heartbeat_event_delivered,
)

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
