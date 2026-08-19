from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import get_db
from ..models import AdminUser, BlockedIp, Domain, WafRule
from ..redis_sync import get_recent_events
from ..templating import templates

router = APIRouter()


@router.get("/")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
):
    domain_count = db.scalar(select(func.count()).select_from(Domain)) or 0
    active_rule_count = db.scalar(
        select(func.count()).select_from(WafRule).where(WafRule.enabled == True)  # noqa: E712
    ) or 0
    blocked_ip_count = db.scalar(select(func.count()).select_from(BlockedIp)) or 0

    events = get_recent_events(limit=200)
    today = datetime.now(timezone.utc).date()
    blocks_today = 0
    for event in events:
        ts = event.get("ts")
        if not ts:
            continue
        try:
            event_date = datetime.fromtimestamp(float(ts), tz=timezone.utc).date()
        except (TypeError, ValueError, OSError):
            continue
        if event_date == today and event.get("action") == "block":
            blocks_today += 1

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "domain_count": domain_count,
            "active_rule_count": active_rule_count,
            "blocked_ip_count": blocked_ip_count,
            "blocks_today": blocks_today,
            "recent_events": events[:20],
        },
    )
