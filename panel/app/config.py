import os
from functools import lru_cache


class Settings:
    database_url: str = os.environ["DATABASE_URL"]
    redis_url: str = os.environ["REDIS_URL"]

    pdns_api_url: str = os.environ["PDNS_API_URL"].rstrip("/")
    pdns_api_key: str = os.environ["PDNS_API_KEY"]
    pdns_default_ns: list[str] = [
        n.strip() for n in os.environ.get("PDNS_DEFAULT_NS", "").split(",") if n.strip()
    ]

    admin_email: str = os.environ["ADMIN_EMAIL"]
    admin_password: str = os.environ["ADMIN_PASSWORD"]
    session_secret: str = os.environ["SESSION_SECRET"]

    edge_public_host: str = os.environ.get("EDGE_PUBLIC_HOST", "")
    # Only used to seed the "acme_email" Setting row on first boot — after
    # that, the panel's Settings page (backed by Postgres, synced to Redis)
    # is the source of truth, not this env var.
    acme_email: str = os.environ.get("ACME_EMAIL", "")

    # Login brute-force protection (see login_guard.py). After
    # login_max_attempts failures from one IP within login_fail_window_seconds,
    # that IP is locked out of /login for login_lockout_base_seconds, doubling
    # on each further violation up to login_lockout_max_seconds.
    login_max_attempts: int = int(os.environ.get("LOGIN_MAX_ATTEMPTS", "5"))
    login_fail_window_seconds: int = int(os.environ.get("LOGIN_FAIL_WINDOW_SECONDS", str(15 * 60)))
    login_lockout_base_seconds: int = int(os.environ.get("LOGIN_LOCKOUT_BASE_SECONDS", str(60 * 60)))
    login_lockout_max_seconds: int = int(os.environ.get("LOGIN_LOCKOUT_MAX_SECONDS", str(24 * 60 * 60)))


@lru_cache
def get_settings() -> Settings:
    return Settings()
