from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import login_guard
from ..auth import login_user, logout_user, verify_password
from ..db import get_db
from ..models import AdminUser
from ..templating import templates

router = APIRouter()


@router.get("/login")
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/", status_code=303)

    remaining = login_guard.seconds_locked_out(login_guard.client_ip(request))
    error = None
    if remaining:
        error = f"Too many failed login attempts. Try again in {login_guard.format_duration(remaining)}."
    return templates.TemplateResponse(request, "login.html", {"error": error}, status_code=429 if remaining else 200)


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = login_guard.client_ip(request)

    remaining = login_guard.seconds_locked_out(ip)
    if remaining:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": f"Too many failed login attempts. Try again in {login_guard.format_duration(remaining)}."},
            status_code=429,
        )

    user = db.scalar(select(AdminUser).where(AdminUser.email == email.lower().strip()))
    if user is None or not verify_password(password, user.password_hash):
        login_guard.record_failure(ip)
        remaining = login_guard.seconds_locked_out(ip)
        if remaining:
            error = f"Too many failed login attempts. Locked out for {login_guard.format_duration(remaining)}."
        else:
            error = "Invalid email or password"
        return templates.TemplateResponse(request, "login.html", {"error": error}, status_code=401)

    login_guard.clear_failures(ip)
    login_user(request, user)
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/login", status_code=303)
