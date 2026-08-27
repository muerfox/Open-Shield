from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import hash_password
from .config import get_settings
from .db import Base, SessionLocal, engine, sync_schema
from .models import AdminUser, Setting
from .redis_sync import sync_all
from .routers import auth, dashboard, dns, domains, logs, settings as settings_router, waf

app = FastAPI(title="Open-Shield")

settings = get_settings()
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    # The panel is HTTPS-only (uvicorn terminates TLS directly — see
    # panel/Dockerfile), so mark the session cookie Secure too: never sent
    # over a plaintext connection even by accident.
    https_only=True,
)

static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.exception_handler(StarletteHTTPException)
async def redirect_unauthenticated(request, exc: StarletteHTTPException):
    if exc.status_code == 303 and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=303)
    raise exc


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    sync_schema()

    db = SessionLocal()
    try:
        if db.query(AdminUser).count() == 0:
            admin = AdminUser(
                email=settings.admin_email.lower().strip(),
                password_hash=hash_password(settings.admin_password),
            )
            db.add(admin)
            db.commit()
        if db.get(Setting, "acme_email") is None:
            db.add(Setting(key="acme_email", value=settings.acme_email))
            db.commit()
        sync_all(db)
    finally:
        db.close()


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(domains.router)
app.include_router(dns.router)
app.include_router(waf.router)
app.include_router(logs.router)
app.include_router(settings_router.router)
