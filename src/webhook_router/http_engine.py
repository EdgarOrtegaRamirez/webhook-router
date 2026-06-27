"""HTTP delivery engine — sends webhooks to HTTP destinations with retry."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import aiohttp

from .models import DestinationConfig, DeliveryResult, RetryStrategy


async def deliver_http(
    destination: DestinationConfig,
    payload: dict[str, Any],
) -> DeliveryResult:
    """Send payload to an HTTP destination with retry logic."""
    start = time.monotonic()
    result = DeliveryResult(
        destination_name=destination.name,
        success=False,
    )

    if destination.retry.strategy == RetryStrategy.NONE:
        return await _attempt(destination, payload, result, start)

    # Retry loop
    for attempt in range(destination.retry.max_retries + 1):
        if attempt > 0:
            delay = destination.retry.get_delay(attempt - 1)
            await _sleep(delay)

        result = await _attempt(destination, payload, result, start)
        if result.success:
            break

        if attempt < destination.retry.max_retries:
            result.attempts = attempt + 2  # initial + retries so far
        else:
            result.attempts = destination.retry.max_retries + 1

    return result


async def _attempt(
    destination: DestinationConfig,
    payload: dict[str, Any],
    result: DeliveryResult,
    start: float,
) -> DeliveryResult:
    """Single HTTP attempt."""
    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "webhook-router/0.1.0",
            **destination.headers,
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=destination.method.value,
                url=destination.url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=destination.timeout),
            ) as resp:
                result.success = 200 <= resp.status < 300
                result.status_code = resp.status
                return result

    except aiohttp.ClientError as e:
        result.error = f"HTTP error: {e}"
        return result
    except asyncio.TimeoutError:
        result.error = f"Timeout after {destination.timeout}s"
        return result


async def _sleep(delay: float) -> None:
    """Async sleep."""
    await asyncio.sleep(delay)
