from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.heartbeat_schemas import (
    HeartbeatCheckInCreate,
    HeartbeatCheckInResponse,
    HeartbeatCreate,
    HeartbeatResponse,
)
from app.persistence.database import get_db_session
from app.services.heartbeat_service import (
    create_heartbeat,
    create_heartbeat_checkin,
    get_heartbeat,
    list_heartbeats,
)

router = APIRouter(
    prefix="/heartbeats",
    tags=["heartbeats"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]


@router.post(
    "",
    response_model=HeartbeatResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_heartbeat_endpoint(
    request: HeartbeatCreate,
    session: DatabaseSession,
) -> HeartbeatResponse:
    heartbeat = create_heartbeat(session, request)
    return HeartbeatResponse.model_validate(heartbeat)


@router.get(
    "",
    response_model=list[HeartbeatResponse],
)
def list_heartbeats_endpoint(
    session: DatabaseSession,
) -> list[HeartbeatResponse]:
    heartbeats = list_heartbeats(session)
    return [HeartbeatResponse.model_validate(h) for h in heartbeats]


@router.get(
    "/{heartbeat_id}",
    response_model=HeartbeatResponse,
)
def get_heartbeat_endpoint(
    heartbeat_id: UUID,
    session: DatabaseSession,
) -> HeartbeatResponse:
    heartbeat = get_heartbeat(session, heartbeat_id)

    if heartbeat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Heartbeat not found",
        )

    return HeartbeatResponse.model_validate(heartbeat)


@router.post(
    "/{heartbeat_id}/checkins",
    response_model=HeartbeatCheckInResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_heartbeat_checkin_endpoint(
    heartbeat_id: UUID,
    request: HeartbeatCheckInCreate,
    session: DatabaseSession,
) -> HeartbeatCheckInResponse:
    checkin = create_heartbeat_checkin(
        session,
        heartbeat_id,
        request,
    )

    if checkin is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Heartbeat not found",
        )

    return HeartbeatCheckInResponse.model_validate(checkin)
