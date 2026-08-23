from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import powerdns_client
from ..auth import require_login
from ..config import get_settings
from ..db import get_db
from ..models import AdminUser, Domain
from ..templating import templates

router = APIRouter(prefix="/dns")

RECORD_TYPES = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"]


def _get_domain_or_404(db: Session, domain_id: int) -> Domain:
    domain = db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


def _ensure_zone(domain: Domain) -> dict:
    zone_name = powerdns_client.zone_for_domain(domain.name)
    zone = powerdns_client.get_zone(zone_name)
    if zone is None:
        zone = powerdns_client.create_zone(zone_name, get_settings().pdns_default_ns)
    return zone


@router.get("")
def list_zones(request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    domains = db.scalars(select(Domain).order_by(Domain.name)).all()
    return templates.TemplateResponse(request, "dns/list.html", {"user": user, "domains": domains})


@router.get("/{domain_id}")
def view_zone(
    domain_id: int, request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)
):
    domain = _get_domain_or_404(db, domain_id)
    zone = _ensure_zone(domain)
    rrsets = sorted(zone.get("rrsets", []), key=lambda rr: (rr["name"], rr["type"]))
    return templates.TemplateResponse(
        request,
        "dns/zone.html",
        {"user": user, "domain": domain, "rrsets": rrsets, "record_types": RECORD_TYPES, "error": None},
    )


@router.post("/{domain_id}/records")
def upsert_record(
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    name: str = Form(...),
    type: str = Form(...),
    contents: str = Form(...),
    ttl: str = Form("3600"),
    priority: str = Form(""),
):
    domain = _get_domain_or_404(db, domain_id)
    ttl_int = int(ttl) if ttl.strip().isdigit() else 3600
    priority_int = int(priority) if priority.strip().isdigit() else None
    values = [line.strip() for line in contents.splitlines() if line.strip()]
    if not values:
        zone = _ensure_zone(domain)
        rrsets = sorted(zone.get("rrsets", []), key=lambda rr: (rr["name"], rr["type"]))
        return templates.TemplateResponse(
            request,
            "dns/zone.html",
            {
                "user": user,
                "domain": domain,
                "rrsets": rrsets,
                "record_types": RECORD_TYPES,
                "error": "Enter at least one record value",
            },
            status_code=400,
        )

    zone_name = powerdns_client.zone_for_domain(domain.name)
    record_name = name.strip() or domain.name
    if not record_name.endswith(zone_name):
        record_name = f"{record_name}.{zone_name}"

    powerdns_client.upsert_rrset(zone_name, record_name, type, ttl_int, values, priority_int)
    return RedirectResponse(f"/dns/{domain_id}", status_code=303)


@router.post("/{domain_id}/records/delete")
def delete_record(
    domain_id: int,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    name: str = Form(...),
    type: str = Form(...),
):
    domain = _get_domain_or_404(db, domain_id)
    zone_name = powerdns_client.zone_for_domain(domain.name)
    powerdns_client.delete_rrset(zone_name, name, type)
    return RedirectResponse(f"/dns/{domain_id}", status_code=303)
