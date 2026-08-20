from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from ..auth import require_login
from ..db import get_db
from ..models import AdminUser, Setting
from ..redis_sync import sync_settings
from ..templating import templates

router = APIRouter(prefix="/settings")

# Let's Encrypt rejects these RFC 2606 "reserved for documentation" domains
# as ACME contact emails (e.g. the .env.example placeholder admin@example.com)
# with an invalidContact error — catch that here instead of a confusing
# failure at cert-issuance time.
_RESERVED_EMAIL_DOMAINS = {"example.com", "example.net", "example.org", "example.edu", "test", "invalid", "localhost"}


def _validate_email(email: str) -> str | None:
    if not email:
        return None
    # This value ends up written into a shell config file that Let's
    # Encrypt's ACME client (dehydrated) sources on the edge — reject
    # anything that could break out of its double-quoted string context.
    if any(c in email for c in '"$`\\\n'):
        return "Email can't contain quotes, backslashes, or $ / ` characters."
    if "@" not in email or "." not in email.split("@", 1)[1]:
        return "That doesn't look like a valid email address."
    domain = email.rsplit("@", 1)[1].lower()
    if domain in _RESERVED_EMAIL_DOMAINS:
        return f"Let's Encrypt rejects '{domain}' as a contact email domain (it's reserved for documentation) — use a real address."
    return None


def _get(db: Session, key: str, default: str = "") -> str:
    setting = db.get(Setting, key)
    return setting.value if setting else default


def _set(db: Session, key: str, value: str) -> None:
    setting = db.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=value)
        db.add(setting)
    else:
        setting.value = value


@router.get("")
def settings_form(request: Request, db: Session = Depends(get_db), user: AdminUser = Depends(require_login)):
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"user": user, "acme_email": _get(db, "acme_email"), "saved": False, "error": None},
    )


@router.post("")
def settings_submit(
    request: Request,
    db: Session = Depends(get_db),
    user: AdminUser = Depends(require_login),
    acme_email: str = Form(""),
):
    acme_email = acme_email.strip()
    error = _validate_email(acme_email)
    if error:
        return templates.TemplateResponse(
            request,
            "settings.html",
            {"user": user, "acme_email": acme_email, "saved": False, "error": error},
            status_code=400,
        )

    _set(db, "acme_email", acme_email)
    db.commit()
    sync_settings(db)
    return templates.TemplateResponse(
        request,
        "settings.html",
        {"user": user, "acme_email": _get(db, "acme_email"), "saved": True, "error": None},
    )
