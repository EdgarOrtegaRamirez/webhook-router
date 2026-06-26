"""Tests for webhook router models."""

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from webhook_router.models import (
    Config,
    DeliveryResult,
    DestinationConfig,
    DestinationType,
    FilterConfig,
    HttpMethod,
    RateLimitConfig,
    RetryConfig,
    RetryStrategy,
    RouteConfig,
    ServerConfig,
    SignatureConfig,
    TransformConfig,
    TransformStrategy,
    WebhookEvent,
)


class TestSignatureConfig:
    """Tests for HMAC signature verification."""

    def test_verify_enabled_no_secret(self):
        sig = SignatureConfig(enabled=True)
        assert not sig.verify(b"payload", "sig")

    def test_verify_disabled_always_passes(self):
        sig = SignatureConfig(enabled=False)
        assert sig.verify(b"payload", "")

    def test_verify_hmac_sha256(self):
        sig = SignatureConfig(enabled=True, secret_env_var="TEST_SECRET")
        import os
        os.environ["TEST_SECRET"] = "mysecret"
        try:
            payload = b"test-payload"
            expected = hmac.new(
                b"mysecret", payload, hashlib.sha256
            ).hexdigest()
            assert sig.verify(payload, expected)
            assert not sig.verify(payload, "wrong-sig")
        finally:
            os.environ.pop("TEST_SECRET", None)

    def test_compute_signature(self):
        sig = SignatureConfig(enabled=True, secret_env_var="TEST_SECRET2")
        import os
        os.environ["TEST_SECRET2"] = "key123"
        try:
            payload = b"hello"
            sig_str = sig.compute_signature(payload)
            assert sig_str == hmac.new(
                b"key123", payload, hashlib.sha256
            ).hexdigest()
        finally:
            os.environ.pop("TEST_SECRET2", None)


class TestFilterConfig:
    """Tests for webhook filtering."""

    def test_match_event_types(self):
        f = FilterConfig(event_types=["push", "pull_request"])
        assert f.matches("push", {}, {})
        assert f.matches("pull_request", {}, {})
        assert not f.matches("issues", {}, {})

    def test_match_no_event_types_matches_all(self):
        f = FilterConfig()
        assert f.matches("any-event", {}, {})

    def test_match_headers(self):
        f = FilterConfig(headers={"X-Debug": "true"})
        assert f.matches(None, {"X-Debug": "true"}, {})
        assert not f.matches(None, {"X-Debug": "false"}, {})
        assert not f.matches(None, {}, {})

    def test_match_payload_keys(self):
        f = FilterConfig(payload_keys={"action": "opened"})
        assert f.matches(None, {}, {"action": "opened"})
        assert not f.matches(None, {}, {"action": "closed"})

    def test_match_nested_payload_keys(self):
        f = FilterConfig(payload_keys={"repository.owner": "edgar"})
        assert f.matches(None, {}, {"repository": {"owner": "edgar"}})
        assert not f.matches(None, {}, {"repository": {"owner": "other"}})
        assert not f.matches(None, {}, {"repository": None})

    def test_match_combined_filters(self):
        f = FilterConfig(
            event_types=["push"],
            headers={"X-Source": "github"},
            payload_keys={"ref": "main"},
        )
        assert f.matches(
            "push",
            {"X-Source": "github"},
            {"ref": "main"},
        )
        assert not f.matches("push", {"X-Source": "github"}, {"ref": "dev"})


class TestTransformConfig:
    """Tests for payload transformation."""

    def test_none_strategy_returns_payload_unchanged(self):
        t = TransformConfig(strategy=TransformStrategy.NONE)
        payload = {"key": "value", "nested": {"a": 1}}
        assert t.transform(payload) == payload

    def test_jinja2_transform(self):
        t = TransformConfig(
            strategy=TransformStrategy.JINJA2,
            template='{"user": "{{ action }}", "repo": "{{ repository.name }}"}',
        )
        payload = {"action": "push", "repository": {"name": "my-repo"}}
        result = t.transform(payload)
        assert result == {"user": "push", "repo": "my-repo"}

    def test_json_path_extract(self):
        t = TransformConfig(
            strategy=TransformStrategy.JSON_PATH,
            json_path="payload.data",
        )
        payload = {"payload": {"data": {"x": 1, "y": 2}}}
        assert t.transform(payload) == {"x": 1, "y": 2}

    def test_json_path_simple(self):
        t = TransformConfig(
            strategy=TransformStrategy.JSON_PATH,
            json_path="name",
        )
        payload = {"name": "test"}
        result = t.transform(payload)
        assert result == {"value": "test"}

    def test_json_path_no_match(self):
        t = TransformConfig(
            strategy=TransformStrategy.JSON_PATH,
            json_path="missing.key",
        )
        assert t.transform({"other": "value"}) == {}


class TestRetryConfig:
    """Tests for retry configuration."""

    def test_no_retry(self):
        r = RetryConfig(strategy=RetryStrategy.NONE)
        assert r.get_delay(0) == 0.0

    def test_fixed_retry(self):
        r = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=2.0)
        assert r.get_delay(0) == 2.0
        assert r.get_delay(5) == 2.0

    def test_exponential_retry(self):
        r = RetryConfig(strategy=RetryStrategy.EXPONENTIAL, base_delay=1.0)
        assert r.get_delay(0) == 1.0
        assert r.get_delay(1) == 2.0
        assert r.get_delay(2) == 4.0
        assert r.get_delay(3) == 8.0

    def test_max_delay_cap(self):
        r = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=10.0,
            max_delay=30.0,
        )
        assert r.get_delay(0) == 10.0
        assert r.get_delay(1) == 20.0
        assert r.get_delay(2) == 30.0  # capped
        assert r.get_delay(10) == 30.0  # capped


class TestConfigValidation:
    """Tests for config model validation."""

    def test_at_least_one_route(self):
        with pytest.raises(ValueError, match="At least one route"):
            Config(routes=[])

    def test_unique_route_names(self):
        with pytest.raises(ValueError, match="unique"):
            Config(
                routes=[
                    RouteConfig(name="same", destinations=[
                        DestinationConfig(name="d1", type=DestinationType.CONSOLE)
                    ]),
                    RouteConfig(name="same", destinations=[
                        DestinationConfig(name="d2", type=DestinationType.CONSOLE)
                    ]),
                ]
            )

    def test_at_least_one_destination(self):
        with pytest.raises(ValueError, match="at least one destination"):
            Config(
                routes=[
                    RouteConfig(name="empty", destinations=[]),
                ]
            )

    def test_valid_config(self):
        config = Config(
            routes=[
                RouteConfig(
                    name="test",
                    destinations=[
                        DestinationConfig(
                            name="dest",
                            type=DestinationType.HTTP,
                            url="http://example.com",
                        )
                    ],
                )
            ]
        )
        assert config.routes[0].name == "test"
        assert config.routes[0].destinations[0].url == "http://example.com"

    def test_full_config(self):
        config = Config.model_validate({
            "server": {
                "host": "0.0.0.0",
                "port": 8080,
                "log_level": "DEBUG",
                "cors_origins": ["https://example.com"],
            },
            "signature": {
                "enabled": True,
                "algorithm": "hmac-sha256",
                "header_name": "X-Hub-Signature",
                "secret_env_var": "SIGNING_SECRET",
            },
            "rate_limit": {
                "enabled": True,
                "requests_per_minute": 60,
                "burst_size": 10,
            },
            "routes": [
                {
                    "name": "webhook-route",
                    "description": "Test route",
                    "filter": {
                        "event_types": ["push"],
                        "headers": {"X-Source": "github"},
                        "payload_keys": {"action": "opened"},
                    },
                    "transform": {
                        "strategy": "jinja2",
                        "template": '{"action": "{{ action }}"}',
                    },
                    "destinations": [
                        {
                            "name": "http-dest",
                            "type": "http",
                            "url": "http://localhost:3000/hook",
                            "method": "POST",
                            "timeout": 15.0,
                            "retry": {
                                "strategy": "exponential",
                                "max_retries": 3,
                                "base_delay": 1.0,
                                "max_delay": 30.0,
                            },
                        },
                        {
                            "name": "file-dest",
                            "type": "file",
                            "file_path": "./logs/webhooks.json",
                        },
                        {
                            "name": "console-dest",
                            "type": "console",
                        },
                    ],
                }
            ],
        })
        assert config.server.port == 8080
        assert config.signature.enabled
        assert config.rate_limit.enabled
        assert len(config.routes) == 1
        assert len(config.routes[0].destinations) == 3


class TestDeliveryResult:
    """Tests for delivery result dataclass."""

    def test_creation(self):
        r = DeliveryResult(
            destination_name="test",
            success=True,
            status_code=200,
            attempts=1,
            duration_ms=45.2,
        )
        assert r.success
        assert r.status_code == 200
        assert r.attempts == 1
