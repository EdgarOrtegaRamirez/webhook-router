"""Webhook server — receives webhooks and routes them."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from aiohttp import web

from .config import Config
from .models import WebhookEvent
from .router import RouterEngine

logger = logging.getLogger(__name__)


class WebhookServer:
    """HTTP server that receives webhooks and routes them."""

    def __init__(self, config: Config):
        self.config = config
        self.engine = RouterEngine(config)
        self.app = web.Application()
        self._setup_routes()
        self._rate_limit_tokens: list[float] = []

    def _setup_routes(self) -> None:
        """Setup aiohttp routes."""
        self.app.router.add_post("/webhook", self.handle_webhook)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/status", self.handle_status)

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """Handle incoming webhook."""
        start = time.monotonic()

        # Check rate limit
        if self.config.rate_limit.enabled:
            if not self._check_rate_limit():
                return web.json_response(
                    {"error": "Rate limit exceeded"},
                    status=429,
                )

        # Read raw body
        raw_body = await request.read()

        # Extract event type
        event_type = request.headers.get("X-Event-Type") or request.headers.get("X-GitHub-Event")
        if not event_type:
            event_type = "unknown"

        # Parse payload
        content_type = request.content_type
        if "json" in content_type:
            try:
                payload = json.loads(raw_body.decode("utf-8"))
            except json.JSONDecodeError as e:
                return web.json_response(
                    {"error": f"Invalid JSON: {e}"},
                    status=400,
                )
        else:
            payload = {"_raw": raw_body.decode("utf-8", errors="replace")}

        # Extract headers (safe subset)
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "content-length")
        }

        # Verify signature if enabled
        if not self._verify_signature(raw_body, request):
            return web.json_response(
                {"error": "Signature verification failed"},
                status=401,
            )

        # Create event
        event = WebhookEvent(
            event_type=event_type,
            headers=headers,
            payload=payload,
            raw_body=raw_body,
        )

        # Process through router
        try:
            results = await self.engine.process(event)
        except Exception as e:
            logger.error("Routing error: %s", e, exc_info=True)
            return web.json_response(
                {"error": "Internal routing error"},
                status=500,
            )

        # Build response
        total_duration = (time.monotonic() - start) * 1000
        response_data = {
            "status": "accepted",
            "event_type": event_type,
            "routes_matched": len(results),
            "total_duration_ms": round(total_duration, 2),
        }

        return web.json_response(response_data, status=202)

    async def handle_health(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({"status": "healthy"})

    async def handle_status(self, request: web.Request) -> web.Response:
        """Status endpoint showing route configuration."""
        return web.json_response(self.engine.get_routes_summary())

    def _verify_signature(self, raw_body: bytes, request: web.Request) -> bool:
        """Verify webhook signature."""
        sig_config = self.config.signature
        if not sig_config.enabled:
            return True

        signature = request.headers.get(sig_config.header_name, "")
        return sig_config.verify(raw_body, signature)

    def _check_rate_limit(self) -> bool:
        """Simple token bucket rate limiter."""
        now = time.monotonic()
        window = 60.0  # 1 minute

        # Clean old tokens
        self._rate_limit_tokens = [
            t for t in self._rate_limit_tokens
            if now - t < window
        ]

        limit = self.config.rate_limit.requests_per_minute
        if len(self._rate_limit_tokens) >= limit:
            return False

        self._rate_limit_tokens.append(now)
        return True

    async def start(self) -> None:
        """Start the webhook server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(
            runner,
            self.config.server.host,
            self.config.server.port,
        )
        logger.info(
            "Webhook router listening on %s:%d",
            self.config.server.host,
            self.config.server.port,
        )
        await site.start()

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()
