"""Core models for webhook routing configuration and runtime data."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────────────

class DestinationType(str, Enum):
    HTTP = "http"
    FILE = "file"
    CONSOLE = "console"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class TransformStrategy(str, Enum):
    JINJA2 = "jinja2"
    JSON_PATH = "json_path"
    NONE = "none"


class RetryStrategy(str, Enum):
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"


# ── Config Models ──────────────────────────────────────────────────────

class SignatureConfig(BaseModel):
    """Webhook signature verification config."""

    algorithm: str = "hmac-sha256"
    header_name: str = "X-Signature"
    secret_env_var: str = "WEBHOOK_SECRET"
    enabled: bool = False

    def verify(self, payload: bytes, signature: str) -> bool:
        """Verify HMAC signature against payload."""
        if not self.enabled:
            return True
        secret = self._get_secret()
        if not secret:
            return False
        expected = self._compute_signature(secret, payload)
        return hmac.compare_digest(expected, signature)

    def compute_signature(self, payload: bytes) -> str:
        """Compute HMAC signature for a payload."""
        secret = self._get_secret()
        if not secret:
            return ""
        return self._compute_signature(secret, payload)

    def _get_secret(self) -> str | None:
        import os
        return os.environ.get(self.secret_env_var)

    def _compute_signature(self, secret: str, payload: bytes) -> str:
        if self.algorithm == "hmac-sha256":
            return hmac.new(
                secret.encode("utf-8"), payload, hashlib.sha256
            ).hexdigest()
        raise ValueError(f"Unsupported signature algorithm: {self.algorithm}")


class FilterConfig(BaseModel):
    """Filter rules for webhook routing."""

    event_types: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    payload_keys: dict[str, Any] = Field(default_factory=dict)

    def matches(self, event_type: str | None, headers: dict[str, str], payload: dict[str, Any]) -> bool:
        """Check if a webhook matches all filter rules."""
        if self.event_types and event_type not in self.event_types:
            return False
        for key, expected in self.headers.items():
            if headers.get(key) != expected:
                return False
        for key, expected in self.payload_keys.items():
            parts = key.split(".")
            value = payload
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                if value is None:
                    return False
            if value != expected:
                return False
        return True


class TransformConfig(BaseModel):
    """Payload transformation config."""

    strategy: TransformStrategy = TransformStrategy.NONE
    template: str = ""
    json_path: str = ""

    def transform(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Transform payload according to strategy."""
        if self.strategy == TransformStrategy.NONE:
            return payload
        if self.strategy == TransformStrategy.JINJA2:
            return self._apply_jinja2(payload)
        if self.strategy == TransformStrategy.JSON_PATH:
            return self._apply_json_path(payload)
        return payload

    def _apply_jinja2(self, payload: dict[str, Any]) -> dict[str, Any]:
        from jinja2 import Template
        t = Template(self.template)
        result = t.render(**payload)
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return {"_transformed": result}

    def _apply_json_path(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Simple JSON path extraction (dot notation)."""
        if not self.json_path:
            return payload
        parts = self.json_path.strip(".").split(".")
        value = payload
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return {}
        if isinstance(value, dict):
            return value
        return {"value": value}


class RetryConfig(BaseModel):
    """Retry configuration for failed deliveries."""

    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt."""
        if self.strategy == RetryStrategy.NONE:
            return 0.0
        if self.strategy == RetryStrategy.FIXED:
            return min(self.base_delay, self.max_delay)
        delay = self.base_delay * (2 ** attempt)
        return min(delay, self.max_delay)


class DestinationConfig(BaseModel):
    """Configuration for a single webhook destination."""

    name: str
    type: DestinationType
    url: str = ""
    file_path: str = ""
    method: HttpMethod = HttpMethod.POST
    headers: dict[str, str] = Field(default_factory=dict)
    timeout: float = 30.0
    retry: RetryConfig = Field(default_factory=RetryConfig)


class RouteConfig(BaseModel):
    """A single route: filter → transform → destinations."""

    name: str
    description: str = ""
    filter: FilterConfig = Field(default_factory=FilterConfig)
    transform: TransformConfig = Field(default_factory=TransformConfig)
    destinations: list[DestinationConfig] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    """Rate limiting for incoming webhooks."""

    enabled: bool = False
    requests_per_minute: int = 100
    burst_size: int = 20


class ServerConfig(BaseModel):
    """Server configuration."""

    host: str = "0.0.0.0"
    port: int = 8080
    secret_env_var: str = "WEBHOOK_SECRET"
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = "INFO"


class Config(BaseModel):
    """Top-level configuration."""

    routes: list[RouteConfig] = Field(default_factory=list)
    server: ServerConfig = Field(default_factory=ServerConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    signature: SignatureConfig = Field(default_factory=SignatureConfig)

    @field_validator("routes")
    @classmethod
    def validate_routes(cls, v: list[RouteConfig]) -> list[RouteConfig]:
        if not v:
            raise ValueError("At least one route is required")
        names = {r.name for r in v}
        if len(names) != len(v):
            raise ValueError("Route names must be unique")
        for route in v:
            if not route.destinations:
                raise ValueError(f"Route '{route.name}' must have at least one destination")
        return v


# ── Runtime Models ─────────────────────────────────────────────────────

@dataclass
class WebhookEvent:
    """A received webhook event."""

    event_type: str | None
    headers: dict[str, str]
    payload: dict[str, Any]
    raw_body: bytes
    received_at: float = field(default_factory=time.time)
    route_name: str = ""


@dataclass
class DeliveryResult:
    """Result of delivering a webhook to a destination."""

    destination_name: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    attempts: int = 0
    duration_ms: float = 0.0


@dataclass
class RouteResult:
    """Result of processing a webhook through a route."""

    route_name: str
    event_type: str | None
    deliveries: list[DeliveryResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
