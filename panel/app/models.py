import datetime
import enum

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class WafTarget(str, enum.Enum):
    url = "url"
    header = "header"
    body = "body"


class WafMatchType(str, enum.Enum):
    contains = "contains"
    regex = "regex"
    exact = "exact"


class WafAction(str, enum.Enum):
    block = "block"
    log = "log"


class Setting(Base):
    """Simple key/value site-wide settings (e.g. the ACME contact email),
    editable from the panel instead of requiring an env var + rebuild.
    Synced to Redis under settings:<key> — see redis_sync.sync_settings.
    """

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    origin_scheme: Mapped[str] = mapped_column(String(8), default="http")
    origin_host: Mapped[str] = mapped_column(String(255))
    origin_port: Mapped[int] = mapped_column(Integer, default=80)

    proxied: Mapped[bool] = mapped_column(Boolean, default=True)
    waf_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # "off" = plain HTTP, no redirect. "auto" = Let's Encrypt via lua-resty-auto-ssl.
    # "manual" = admin-pasted PEM cert/key (ssl_cert/ssl_key).
    ssl_mode: Mapped[str] = mapped_column(String(16), default="off")
    ssl_cert: Mapped[str | None] = mapped_column(Text, nullable=True)
    ssl_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    cache_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    cache_ttl_seconds: Mapped[int] = mapped_column(Integer, default=60)

    rate_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    rate_limit_requests: Mapped[int] = mapped_column(Integer, default=100)
    rate_limit_window_seconds: Mapped[int] = mapped_column(Integer, default=10)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    waf_rules: Mapped[list["WafRule"]] = relationship(back_populates="domain", cascade="all, delete-orphan")
    blocked_ips: Mapped[list["BlockedIp"]] = relationship(back_populates="domain", cascade="all, delete-orphan")


class WafRule(Base):
    __tablename__ = "waf_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL domain_id = applies globally, to every domain.
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=True)

    name: Mapped[str] = mapped_column(String(255))
    target: Mapped[str] = mapped_column(String(16))  # WafTarget
    match_type: Mapped[str] = mapped_column(String(16))  # WafMatchType
    header_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(16), default=WafAction.block.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped[Domain | None] = relationship(back_populates="waf_rules")


class BlockedIp(Base):
    __tablename__ = "blocked_ips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL domain_id = blocked globally, across every domain.
    domain_id: Mapped[int | None] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"), nullable=True)

    ip_or_cidr: Mapped[str] = mapped_column(String(64))
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    domain: Mapped[Domain | None] = relationship(back_populates="blocked_ips")
