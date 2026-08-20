"""Brute-force protection for /login.

Failures are tracked per client IP in Redis. After `login_max_attempts`
failures within `login_fail_window_seconds`, the IP is locked out of
/login entirely (no password check even attempted) for
`login_lockout_base_seconds`, doubling on each further violation up to
`login_lockout_max_seconds`. A successful login clears both the failure
count and the escalation level for that IP.
"""

from fastapi import Request

from .config import get_settings
from .redis_sync import get_redis


def _fail_key(ip: str) -> str:
    return f"login:fails:{ip}"


def _lockout_key(ip: str) -> str:
    return f"login:lockout:{ip}"


def _lockout_level_key(ip: str) -> str:
    return f"login:lockout_level:{ip}"


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def seconds_locked_out(ip: str) -> int:
    """0 if not locked out, otherwise seconds remaining."""
    ttl = get_redis().ttl(_lockout_key(ip))
    return ttl if ttl and ttl > 0 else 0


def format_duration(seconds: int) -> str:
    if seconds >= 3600:
        hours = (seconds + 3599) // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    minutes = max(1, (seconds + 59) // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


def record_failure(ip: str) -> None:
    settings = get_settings()
    r = get_redis()

    key = _fail_key(ip)
    count = r.incr(key)
    if count == 1:
        r.expire(key, settings.login_fail_window_seconds)

    if count >= settings.login_max_attempts:
        level = r.incr(_lockout_level_key(ip))
        r.expire(_lockout_level_key(ip), 7 * 24 * 3600)
        duration = min(
            settings.login_lockout_base_seconds * (2 ** (level - 1)),
            settings.login_lockout_max_seconds,
        )
        r.set(_lockout_key(ip), "1", ex=duration)
        r.delete(key)


def clear_failures(ip: str) -> None:
    r = get_redis()
    r.delete(_fail_key(ip))
    r.delete(_lockout_level_key(ip))
    r.delete(_lockout_key(ip))
