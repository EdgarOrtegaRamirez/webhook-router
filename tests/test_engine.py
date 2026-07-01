"""Tests for webhook router engine."""

import asyncio
from pathlib import Path


from webhook_router.models import (
    Config,
    DestinationConfig,
    DestinationType,
    RouteConfig,
    WebhookEvent,
)
from webhook_router.router import RouterEngine


class TestRouterEngine:
    """Tests for the routing engine."""

    def _make_config(self, routes: list[RouteConfig]) -> Config:
        return Config(routes=routes)

    def test_match_and_dispatch_console(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="test",
                    filter={"event_types": ["push"]},
                    destinations=[
                        DestinationConfig(name="console", type=DestinationType.CONSOLE),
                    ],
                )
            ]
        )
        engine = RouterEngine(config)
        event = WebhookEvent(
            event_type="push",
            headers={},
            payload={"ref": "main"},
            raw_body=b'{"ref": "main"}',
        )

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1
        assert results[0].route_name == "test"
        assert len(results[0].deliveries) == 1
        assert results[0].deliveries[0].success

    def test_no_match_skips_route(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="push-only",
                    filter={"event_types": ["push"]},
                    destinations=[
                        DestinationConfig(name="console", type=DestinationType.CONSOLE),
                    ],
                )
            ]
        )
        engine = RouterEngine(config)
        event = WebhookEvent(
            event_type="issues",
            headers={},
            payload={"action": "opened"},
            raw_body=b'{"action": "opened"}',
        )

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 0

    def test_multiple_destinations(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="multi",
                    destinations=[
                        DestinationConfig(name="console1", type=DestinationType.CONSOLE),
                        DestinationConfig(name="file", type=DestinationType.FILE, file_path="./logs/test.json"),
                    ],
                )
            ]
        )
        engine = RouterEngine(config)
        event = WebhookEvent(
            event_type="push",
            headers={},
            payload={"test": True},
            raw_body=b'{"test": true}',
        )

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1
        assert len(results[0].deliveries) == 2
        assert all(d.success for d in results[0].deliveries)

        # Cleanup
        Path("./logs/test.json").unlink(missing_ok=True)

    def test_transform_jinja2(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="transformed",
                    destinations=[
                        DestinationConfig(name="console", type=DestinationType.CONSOLE),
                    ],
                )
            ]
        )
        config.routes[0].transform.strategy = "jinja2"
        config.routes[0].transform.template = '{"event": "{{ event_type }}"}'

        engine = RouterEngine(config)
        event = WebhookEvent(
            event_type="push",
            headers={},
            payload={"event_type": "push", "repo": "test"},
            raw_body=b'{"event_type": "push"}',
        )

        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1
        assert results[0].deliveries[0].success

    def test_filter_by_headers(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="debug-only",
                    filter={"headers": {"X-Debug": "true"}},
                    destinations=[
                        DestinationConfig(name="console", type=DestinationType.CONSOLE),
                    ],
                )
            ]
        )
        engine = RouterEngine(config)

        # Should match
        event = WebhookEvent(
            event_type="push",
            headers={"X-Debug": "true"},
            payload={},
            raw_body=b"{}",
        )
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1

        # Should not match
        event2 = WebhookEvent(
            event_type="push",
            headers={"X-Debug": "false"},
            payload={},
            raw_body=b"{}",
        )
        loop2 = asyncio.new_event_loop()
        try:
            results2 = loop2.run_until_complete(engine.process(event2))
        finally:
            loop2.close()
        assert len(results2) == 0

    def test_filter_by_payload_keys(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="opened-only",
                    filter={"payload_keys": {"action": "opened"}},
                    destinations=[
                        DestinationConfig(name="console", type=DestinationType.CONSOLE),
                    ],
                )
            ]
        )
        engine = RouterEngine(config)

        event = WebhookEvent(
            event_type="pull_request",
            headers={},
            payload={"action": "opened"},
            raw_body=b'{"action": "opened"}',
        )
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1

        event2 = WebhookEvent(
            event_type="pull_request",
            headers={},
            payload={"action": "closed"},
            raw_body=b'{"action": "closed"}',
        )
        loop2 = asyncio.new_event_loop()
        try:
            results2 = loop2.run_until_complete(engine.process(event2))
        finally:
            loop2.close()
        assert len(results2) == 0

    def test_multiple_routes(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="push-route",
                    filter={"event_types": ["push"]},
                    destinations=[
                        DestinationConfig(name="c1", type=DestinationType.CONSOLE),
                    ],
                ),
                RouteConfig(
                    name="pr-route",
                    filter={"event_types": ["pull_request"]},
                    destinations=[
                        DestinationConfig(name="c2", type=DestinationType.CONSOLE),
                    ],
                ),
            ]
        )
        engine = RouterEngine(config)

        event = WebhookEvent(
            event_type="push",
            headers={},
            payload={},
            raw_body=b"{}",
        )
        loop = asyncio.new_event_loop()
        try:
            results = loop.run_until_complete(engine.process(event))
        finally:
            loop.close()
        assert len(results) == 1
        assert results[0].route_name == "push-route"

    def test_get_routes_summary(self):
        config = self._make_config(
            [
                RouteConfig(
                    name="route1",
                    filter={"event_types": ["push"]},
                    destinations=[
                        DestinationConfig(name="d1", type=DestinationType.HTTP, url="http://example.com"),
                        DestinationConfig(name="d2", type=DestinationType.FILE, file_path="./logs.json"),
                    ],
                ),
            ]
        )
        engine = RouterEngine(config)
        summary = engine.get_routes_summary()
        assert summary["total_routes"] == 1
        assert len(summary["routes"][0]["destinations"]) == 2
        assert summary["routes"][0]["destinations"][0]["type"] == "http"
        assert summary["routes"][0]["destinations"][1]["type"] == "file"
