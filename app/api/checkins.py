from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.persistence.database import get_db_session
from app.services.checkin_token_service import redeem_checkin_token


router = APIRouter(
    prefix="/checkins",
    tags=["check-ins"],
)

DatabaseSession = Annotated[Session, Depends(get_db_session)]

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates",
)


@router.get(
    "/{token}",
    response_class=HTMLResponse,
)
def show_checkin_confirmation(
    request: Request,
    token: str,
) -> HTMLResponse:
    """Display a confirmation page without validating or consuming the token."""
    return templates.TemplateResponse(
        request=request,
        name="checkin_confirm.html",
        context={
            "token": token,
        },
    )


@router.post(
    "/{token}",
    response_class=HTMLResponse,
)
def confirm_checkin(
    request: Request,
    token: str,
    session: DatabaseSession,
) -> HTMLResponse:
    """Redeem a token after the user explicitly confirms the check-in."""
    checkin = redeem_checkin_token(
        session,
        token,
    )

    if checkin is None:
        return templates.TemplateResponse(
            request=request,
            name="checkin_unavailable.html",
            context={},
        )

    return templates.TemplateResponse(
        request=request,
        name="checkin_success.html",
        context={},
    )
