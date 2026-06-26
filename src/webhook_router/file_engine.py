"""File and console delivery engines."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .models import DestinationConfig, DeliveryResult

logger = logging.getLogger(__name__)


async def deliver_file(
    destination: DestinationConfig,
    payload: dict[str, Any],
) -> DeliveryResult:
    """Write payload to a file."""
    start = time.monotonic()
    result = DeliveryResult(
        destination_name=destination.name,
        success=False,
    )

    try:
        file_path = Path(destination.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Append mode with JSON array
        existing = []
        if file_path.exists():
            try:
                existing = json.loads(file_path.read_text(encoding="utf-8"))
                if not isinstance(existing, list):
                    existing = [existing]
            except (json.JSONDecodeError, ValueError):
                existing = []

        existing.append(payload)
        file_path.write_text(
            json.dumps(existing, indent=2, default=str),
            encoding="utf-8",
        )

        result.success = True
        result.status_code = 201
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    except OSError as e:
        result.error = f"File write error: {e}"
        result.duration_ms = (time.monotonic() - start) * 1000
        logger.error("File delivery failed for %s: %s", destination.name, e)
        return result


async def deliver_console(
    destination: DestinationConfig,
    payload: dict[str, Any],
) -> DeliveryResult:
    """Log payload to console (via Python logging)."""
    start = time.monotonic()
    result = DeliveryResult(
        destination_name=destination.name,
        success=True,
        status_code=200,
    )

    try:
        logger.info(
            "Webhook routed to %s: %s",
            destination.name,
            json.dumps(payload, default=str),
        )
        result.duration_ms = (time.monotonic() - start) * 1000
        return result

    except Exception as e:
        result.success = False
        result.error = str(e)
        result.duration_ms = (time.monotonic() - start) * 1000
        return result
