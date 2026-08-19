"""Thin wrapper around the PowerDNS Authoritative HTTP API (server id "localhost").

Zone/record names in the PowerDNS API are always fully-qualified with a
trailing dot (e.g. "example.com."); helpers here accept names with or
without the dot and normalize.
"""

import httpx

from .config import get_settings


def _fqdn(name: str) -> str:
    name = name.strip().lower()
    return name if name.endswith(".") else f"{name}."


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        base_url=f"{settings.pdns_api_url}/servers/localhost",
        headers={"X-API-Key": settings.pdns_api_key},
        timeout=10.0,
    )


def list_zones() -> list[dict]:
    with _client() as c:
        r = c.get("/zones")
        r.raise_for_status()
        return r.json()


def get_zone(name: str) -> dict | None:
    with _client() as c:
        r = c.get(f"/zones/{_fqdn(name)}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def create_zone(name: str, nameservers: list[str]) -> dict:
    payload = {
        "name": _fqdn(name),
        "kind": "Native",
        "masters": [],
        "nameservers": [_fqdn(ns) for ns in nameservers] or [_fqdn(name)],
    }
    with _client() as c:
        r = c.post("/zones", json=payload)
        r.raise_for_status()
        return r.json()


def delete_zone(name: str) -> None:
    with _client() as c:
        r = c.delete(f"/zones/{_fqdn(name)}")
        if r.status_code not in (204, 404):
            r.raise_for_status()


def upsert_rrset(
    zone: str,
    record_name: str,
    record_type: str,
    ttl: int,
    contents: list[str],
    priority: int | None = None,
) -> None:
    """Replace (or create) the RRset for (record_name, record_type) with `contents`."""
    record_type = record_type.upper()
    if record_type == "MX" and priority is not None:
        formatted = [f"{priority} {c}" for c in contents]
    else:
        formatted = contents
    payload = {
        "rrsets": [
            {
                "name": _fqdn(record_name),
                "type": record_type,
                "ttl": ttl,
                "changetype": "REPLACE",
                "records": [{"content": c, "disabled": False} for c in formatted],
            }
        ]
    }
    with _client() as c:
        r = c.patch(f"/zones/{_fqdn(zone)}", json=payload)
        r.raise_for_status()


def delete_rrset(zone: str, record_name: str, record_type: str) -> None:
    payload = {
        "rrsets": [
            {"name": _fqdn(record_name), "type": record_type.upper(), "changetype": "DELETE"}
        ]
    }
    with _client() as c:
        r = c.patch(f"/zones/{_fqdn(zone)}", json=payload)
        r.raise_for_status()


def set_proxied_a_record(zone: str, edge_host: str, ttl: int = 300) -> None:
    """Point a proxied domain's apex A record at the Open-Shield edge."""
    upsert_rrset(zone, zone, "A", ttl, [edge_host])
