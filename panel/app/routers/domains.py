from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import powerdns_client
from ..auth import require_login
from ..config import get_settings
from ..db import get_db
from ..models import AdminUser, Domain
from ..redis_sync import delete_domain, push_domain_and_rules
from ..templating import templates

router = APIRouter(prefix="/domains")


def _get_domain_or_404(db: Session, domain_id: int) -> Domain:
    domain = db.get(Domain, domain_id)
    if domain is None:
        raise HTTPException(status_code=404, detail="Domain not found")
    return domain


def _apply_dns_for_proxy(domain: Domain) -> None:
    """Ensure a PowerDNS zone exists for the domain, and if proxying is on,
    point its apex A record at the Open-Shield edge."""
    settings = get_settings()
    zone = powerdns_client.get_zone(domain.name)
    if zone is None:
        powerdns_client.create_zone(domain.name, settings.pdns_default_ns)
    if domain.proxied and settings.edge_public_host:
        powerdns_client.set_proxied_a_record(domain.name, settings.edge_public_host)


def _validate_ssl(ssl_mode: str, ssl_cert: str, ssl_key: str) -> str | None:
    if ssl_mode not in ("off", "auto", "manual"):
        return "Invalid SSL mode"
    if ssl_mode == "manual":
        if "BEGIN CERTIFICATE" not in ssl_cert:
            return "Paste a PEM certificate (must contain 'BEGIN CERTIFICATE')"
        if "PRIVATE KEY" not in ssl_key:
            return "Paste a PEM private key (must contain 'BEGIN ... PRIVATE KEY')"
    return None


def _resolve_ssl_fields(
    ssl_mode: str, ssl_cert: str, ssl_key: str, existing: Domain | None
) -> tuple[str | None, str | None]:
    """For manual mode, blank textareas on an edit mean 'keep the existing
    cert/key' rather than wiping them out."""
    cert = ssl_cert.strip()
    key = ssl_key.strip()
    if ssl_mode == "manual" and existing is not None:
        cert = cert or existing.ssl_cert or ""
        key = key or existing.ssl_key or ""
    if ssl_mode != "manual":
        return None, None
    return cert, key


@router.get("")
def list_domains(request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    domains = db.scalars(select(Domain).order_by(Domain.name)).all()
    return templates.TemplateResponse(request, "domains/list.html", {"user": user, "domains": domains})


@router.get("/new")
def new_domain_form(request: Request, user: AdminUser = Depends(require_login)):
    return templates.TemplateResponse(request, "domains/form.html", {"user": user, "domain": None, "error": None})


@router.post("/new")
def create_domain(
    request: Request,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    name: str = Form(...),
    origin_scheme: str = Form("http"),
    origin_host: str = Form(...),
    origin_port: int = Form(80),
    proxied: bool = Form(False),
    waf_enabled: bool = Form(False),
    ssl_mode: str = Form("off"),
    ssl_cert: str = Form(""),
    ssl_key: str = Form(""),
    cache_enabled: bool = Form(False),
    cache_ttl_seconds: int = Form(60),
    rate_limit_enabled: bool = Form(False),
    rate_limit_requests: int = Form(100),
    rate_limit_window_seconds: int = Form(10),
):
    name = name.lower().strip().rstrip(".")
    existing = db.scalar(select(Domain).where(Domain.name == name))
    if existing is not None:
        return templates.TemplateResponse(
            request,
            "domains/form.html",
            {"user": user, "domain": None, "error": f"Domain '{name}' already exists"},
            status_code=400,
        )

    resolved_cert, resolved_key = _resolve_ssl_fields(ssl_mode, ssl_cert, ssl_key, None)
    ssl_error = _validate_ssl(ssl_mode, resolved_cert or "", resolved_key or "")
    if ssl_error:
        return templates.TemplateResponse(
            request, "domains/form.html", {"user": user, "domain": None, "error": ssl_error}, status_code=400
        )

    domain = Domain(
        name=name,
        origin_scheme=origin_scheme,
        origin_host=origin_host.strip(),
        origin_port=origin_port,
        proxied=proxied,
        waf_enabled=waf_enabled,
        ssl_mode=ssl_mode,
        ssl_cert=resolved_cert,
        ssl_key=resolved_key,
        cache_enabled=cache_enabled,
        cache_ttl_seconds=cache_ttl_seconds,
        rate_limit_enabled=rate_limit_enabled,
        rate_limit_requests=rate_limit_requests,
        rate_limit_window_seconds=rate_limit_window_seconds,
    )
    db.add(domain)
    db.commit()
    db.refresh(domain)

    _apply_dns_for_proxy(domain)
    push_domain_and_rules(db, domain)

    return RedirectResponse("/domains", status_code=303)


@router.get("/{domain_id}/edit")
def edit_domain_form(
    domain_id: int, request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)
):
    domain = _get_domain_or_404(db, domain_id)
    return templates.TemplateResponse(request, "domains/form.html", {"user": user, "domain": domain, "error": None})


@router.post("/{domain_id}/edit")
def update_domain(
    domain_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    origin_scheme: str = Form("http"),
    origin_host: str = Form(...),
    origin_port: int = Form(80),
    proxied: bool = Form(False),
    waf_enabled: bool = Form(False),
    ssl_mode: str = Form("off"),
    ssl_cert: str = Form(""),
    ssl_key: str = Form(""),
    cache_enabled: bool = Form(False),
    cache_ttl_seconds: int = Form(60),
    rate_limit_enabled: bool = Form(False),
    rate_limit_requests: int = Form(100),
    rate_limit_window_seconds: int = Form(10),
):
    domain = _get_domain_or_404(db, domain_id)

    resolved_cert, resolved_key = _resolve_ssl_fields(ssl_mode, ssl_cert, ssl_key, domain)
    ssl_error = _validate_ssl(ssl_mode, resolved_cert or "", resolved_key or "")
    if ssl_error:
        return templates.TemplateResponse(
            request, "domains/form.html", {"user": user, "domain": domain, "error": ssl_error}, status_code=400
        )

    domain.origin_scheme = origin_scheme
    domain.origin_host = origin_host.strip()
    domain.origin_port = origin_port
    domain.proxied = proxied
    domain.waf_enabled = waf_enabled
    domain.ssl_mode = ssl_mode
    domain.ssl_cert = resolved_cert
    domain.ssl_key = resolved_key
    domain.cache_enabled = cache_enabled
    domain.cache_ttl_seconds = cache_ttl_seconds
    domain.rate_limit_enabled = rate_limit_enabled
    domain.rate_limit_requests = rate_limit_requests
    domain.rate_limit_window_seconds = rate_limit_window_seconds
    db.commit()
    db.refresh(domain)

    _apply_dns_for_proxy(domain)
    push_domain_and_rules(db, domain)

    return RedirectResponse("/domains", status_code=303)


@router.post("/{domain_id}/delete")
def delete_domain_route(
    domain_id: int, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)
):
    domain = _get_domain_or_404(db, domain_id)
    name = domain.name
    db.delete(domain)
    db.commit()
    delete_domain(name)
    return RedirectResponse("/domains", status_code=303)
