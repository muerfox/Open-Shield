from fastapi import APIRouter, Depends, Request

from ..auth import require_login
from ..models import AdminUser
from ..redis_sync import get_recent_events
from ..templating import templates

router = APIRouter(prefix="/logs")


@router.get("")
def logs_page(request: Request, user: AdminUser = Depends(require_login)):
    events = get_recent_events(limit=200)
    return templates.TemplateResponse(request, "logs/index.html", {"user": user, "events": events})


@router.get("/partial")
def logs_partial(request: Request, user: AdminUser = Depends(require_login)):
    events = get_recent_events(limit=200)
    return templates.TemplateResponse(request, "logs/_rows.html", {"events": events})
