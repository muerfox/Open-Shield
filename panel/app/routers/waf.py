from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import get_db
from ..models import AdminUser, BlockedIp, Domain, WafRule
from ..redis_sync import sync_blocked_ips, sync_waf_rules
from ..templating import templates

router = APIRouter(prefix="/waf")

TARGETS = ["url", "header", "body"]
MATCH_TYPES = ["contains", "regex", "exact"]
ACTIONS = ["block", "log"]


@router.get("")
def waf_home(request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    rules = db.scalars(select(WafRule).order_by(WafRule.id.desc())).all()
    blocked_ips = db.scalars(select(BlockedIp).order_by(BlockedIp.id.desc())).all()
    domains = db.scalars(select(Domain).order_by(Domain.name)).all()
    return templates.TemplateResponse(
        request,
        "waf/index.html",
        {
            "user": user,
            "rules": rules,
            "blocked_ips": blocked_ips,
            "domains": domains,
            "targets": TARGETS,
            "match_types": MATCH_TYPES,
            "actions": ACTIONS,
            "error": None,
        },
    )


@router.post("/rules/new")
def create_rule(
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    name: str = Form(...),
    domain_id: str = Form(""),
    target: str = Form(...),
    match_type: str = Form(...),
    header_name: str = Form(""),
    value: str = Form(...),
    action: str = Form("block"),
):
    rule = WafRule(
        name=name.strip(),
        domain_id=int(domain_id) if domain_id else None,
        target=target,
        match_type=match_type,
        header_name=header_name.strip() or None,
        value=value,
        action=action,
        enabled=True,
    )
    db.add(rule)
    db.commit()
    sync_waf_rules(db)
    return RedirectResponse("/waf", status_code=303)


@router.post("/rules/{rule_id}/toggle")
def toggle_rule(rule_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    rule = db.get(WafRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404)
    rule.enabled = not rule.enabled
    db.commit()
    sync_waf_rules(db)
    return RedirectResponse("/waf", status_code=303)


@router.post("/rules/{rule_id}/delete")
def delete_rule(rule_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    rule = db.get(WafRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404)
    db.delete(rule)
    db.commit()
    sync_waf_rules(db)
    return RedirectResponse("/waf", status_code=303)


@router.post("/ips/new")
def add_blocked_ip(
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    ip_or_cidr: str = Form(...),
    domain_id: str = Form(""),
    note: str = Form(""),
):
    entry = BlockedIp(
        ip_or_cidr=ip_or_cidr.strip(),
        domain_id=int(domain_id) if domain_id else None,
        note=note.strip() or None,
    )
    db.add(entry)
    db.commit()
    sync_blocked_ips(db)
    return RedirectResponse("/waf", status_code=303)


@router.post("/ips/{ip_id}/delete")
def delete_blocked_ip(ip_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    entry = db.get(BlockedIp, ip_id)
    if entry is None:
        raise HTTPException(status_code=404)
    db.delete(entry)
    db.commit()
    sync_blocked_ips(db)
    return RedirectResponse("/waf", status_code=303)
