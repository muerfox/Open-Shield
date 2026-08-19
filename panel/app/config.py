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


@lru_cache
def get_settings() -> Settings:
    return Settings()
