"""Pushes panel (Postgres) config into Redis in the flattened shape that
OpenResty's Lua modules read on the request hot path. Redis is treated as a
disposable cache of Postgres — `sync_all` can always rebuild it from scratch.
"""

import json
from functools import lru_cache

import redis
from sqlalchemy.orm import Session

from .config import get_settings
from .models import BlockedIp, Domain, WafRule


@lru_cache
def get_redis() -> redis.Redis:
    return redis.from_url(get_settings().redis_url, decode_responses=True)


def _domain_key(name: str) -> str:
    return f"domain:{name.lower()}"


def sync_domain(domain: Domain) -> None:
    r = get_redis()
    name = domain.name.lower()
    key = _domain_key(name)
    r.hset(
        key,
        mapping={
            "origin_scheme": domain.origin_scheme,
            "origin_host": domain.origin_host,
            "origin_port": str(domain.origin_port),
            "proxied": "1" if domain.proxied else "0",
            "waf_enabled": "1" if domain.waf_enabled else "0",
            "ssl_mode": domain.ssl_mode,
            "cache_enabled": "1" if domain.cache_enabled else "0",
            "cache_ttl": str(domain.cache_ttl_seconds),
            "rate_limit_enabled": "1" if domain.rate_limit_enabled else "0",
            "rate_limit_requests": str(domain.rate_limit_requests),
            "rate_limit_window": str(domain.rate_limit_window_seconds),
        },
    )
    r.sadd("domains:index", name)

    cert_key = f"domain:{name}:ssl_cert"
    priv_key = f"domain:{name}:ssl_key"
    if domain.ssl_mode == "manual" and domain.ssl_cert and domain.ssl_key:
        r.set(cert_key, domain.ssl_cert)
        r.set(priv_key, domain.ssl_key)
    else:
        r.delete(cert_key, priv_key)


def delete_domain(name: str) -> None:
    r = get_redis()
    name = name.lower()
    r.delete(_domain_key(name))
    r.delete(f"domain:{name}:ssl_cert")
    r.delete(f"domain:{name}:ssl_key")
    r.delete(f"waf:blocked_ips:{name}")
    r.delete(f"waf:blocked_cidrs:{name}")
    r.srem("domains:index", name)


def sync_waf_rules(db: Session) -> None:
    """Full rebuild of the `waf:rules` list from Postgres."""
    r = get_redis()
    rules = db.query(WafRule).filter(WafRule.enabled == True).all()  # noqa: E712
    payload = []
    for rule in rules:
        payload.append(
            {
                "id": rule.id,
                "name": rule.name,
                "domain": rule.domain.name.lower() if rule.domain else None,
                "target": rule.target,
                "match_type": rule.match_type,
                "header_name": rule.header_name,
                "value": rule.value,
                "action": rule.action,
            }
        )
    r.set("waf:rules", json.dumps(payload))


def sync_blocked_ips(db: Session) -> None:
    """Full rebuild of blocked-IP sets/CIDR lists, global + per-domain."""
    r = get_redis()

    for key in r.keys("waf:blocked_ips:*"):
        r.delete(key)
    for key in r.keys("waf:blocked_cidrs:*"):
        r.delete(key)

    exact: dict[str, set[str]] = {"global": set()}
    cidrs: dict[str, list[str]] = {"global": []}

    for entry in db.query(BlockedIp).all():
        scope = entry.domain.name.lower() if entry.domain else "global"
        exact.setdefault(scope, set())
        cidrs.setdefault(scope, [])
        if "/" in entry.ip_or_cidr:
            cidrs[scope].append(entry.ip_or_cidr)
        else:
            exact[scope].add(entry.ip_or_cidr)

    for scope, ips in exact.items():
        if ips:
            r.sadd(f"waf:blocked_ips:{scope}", *ips)
    for scope, cidr_list in cidrs.items():
        if cidr_list:
            r.set(f"waf:blocked_cidrs:{scope}", json.dumps(cidr_list))


def sync_all(db: Session) -> None:
    for domain in db.query(Domain).all():
        sync_domain(domain)
    sync_waf_rules(db)
    sync_blocked_ips(db)


def push_domain_and_rules(db: Session, domain: Domain) -> None:
    """Convenience used by routers after any change touching one domain."""
    sync_domain(domain)
    sync_waf_rules(db)
    sync_blocked_ips(db)


def get_recent_events(limit: int = 100) -> list[dict]:
    """Reads the capped WAF event feed that openresty/lua/waf.lua pushes to."""
    r = get_redis()
    raw = r.lrange("waf:log", 0, limit - 1)
    events = []
    for item in raw:
        try:
            events.append(json.loads(item))
        except (TypeError, ValueError):
            continue
    return events
