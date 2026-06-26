"""Router engine — matches events to routes and dispatches to destinations."""

from __future__ import annotations

import logging
import time
from typing import Any

from .models import (
    Config,
    DeliveryResult,
    DestinationConfig,
    DestinationType,
    RouteConfig,
    RouteResult,
    WebhookEvent,
)
from .file_engine import deliver_console, deliver_file
from .http_engine import deliver_http

logger = logging.getLogger(__name__)


class RouterEngine:
    """Main routing engine that matches webhooks to routes and dispatches."""

    def __init__(self, config: Config):
        self.config = config
        self.routes = config.routes

    async def process(self, event: WebhookEvent) -> list[RouteResult]:
        """Process a webhook event through all matching routes."""
        results = []

        # Apply rate limiting if enabled
        if self.config.rate_limit.enabled:
            # Token bucket check — simplified for now
            pass

        for route in self.routes:
            if not self._matches(event, route):
                continue

            logger.info(
                "Webhook event '%s' matched route '%s'",
                event.event_type,
                route.name,
            )

            # Transform payload
            transformed = route.transform.transform(event.payload)

            # Dispatch to all destinations
            deliveries = await self._dispatch(route, transformed)

            result = RouteResult(
                route_name=route.name,
                event_type=event.event_type,
                deliveries=deliveries,
            )
            results.append(result)

        return results

    def _matches(self, event: WebhookEvent, route: RouteConfig) -> bool:
        """Check if event matches route filter."""
        return route.filter.matches(
            event_type=event.event_type,
            headers=event.headers,
            payload=event.payload,
        )

    async def _dispatch(
        self,
        route: RouteConfig,
        payload: dict[str, Any],
    ) -> list[DeliveryResult]:
        """Dispatch payload to all destinations in a route."""
        deliveries = []

        for dest in route.destinations:
            delivery = await self._send_to_destination(dest, payload)
            deliveries.append(delivery)

            if not delivery.success:
                logger.warning(
                    "Failed to deliver to '%s': %s",
                    delivery.destination_name,
                    delivery.error,
                )

        return deliveries

    async def _send_to_destination(
        self,
        dest: DestinationConfig,
        payload: dict[str, Any],
    ) -> DeliveryResult:
        """Send payload to a single destination."""
        start = time.monotonic()

        if dest.type == DestinationType.HTTP:
            result = await deliver_http(dest, payload)
        elif dest.type == DestinationType.FILE:
            result = await deliver_file(dest, payload)
        elif dest.type == DestinationType.CONSOLE:
            result = await deliver_console(dest, payload)
        else:
            result = DeliveryResult(
                destination_name=dest.name,
                success=False,
                error=f"Unknown destination type: {dest.type}",
            )

        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    def get_routes_summary(self) -> dict[str, Any]:
        """Return summary info about configured routes."""
        return {
            "total_routes": len(self.routes),
            "routes": [
                {
                    "name": r.name,
                    "description": r.description,
                    "event_types": r.filter.event_types,
                    "destinations": [
                        {
                            "name": d.name,
                            "type": d.type.value,
                            "url": d.url or d.file_path,
                        }
                        for d in r.destinations
                    ],
                }
                for r in self.routes
            ],
        }
