"""CLI interface for webhook-router."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

from .config import load_config
from .models import Config, RouteConfig, FilterConfig, DestinationConfig, DestinationType
from .server import WebhookServer
from .__init__ import __version__

logger = logging.getLogger(__name__)

SAMPLE_CONFIG = """\
# Webhook Router Configuration
# ─────────────────────────────────────────────────────────────

# Server settings
server:
  host: "0.0.0.0"
  port: 8080
  log_level: "INFO"
  cors_origins: ["*"]

# Webhook signature verification (optional)
signature:
  enabled: true
  algorithm: "hmac-sha256"
  header_name: "X-Signature"
  secret_env_var: "WEBHOOK_SECRET"

# Rate limiting (optional)
rate_limit:
  enabled: false
  requests_per_minute: 100
  burst_size: 20

# Routes — each route matches events and dispatches to destinations
routes:
  - name: "github-events"
    description: "Route GitHub webhooks to internal API"
    filter:
      event_types: ["push", "pull_request", "issues"]
      headers:
        X-GitHub-Event: "push"
      payload_keys: {}
    transform:
      strategy: "jinja2"
      template: "{% raw %}{{ payload }}{% endraw %}"
    destinations:
      - name: "api-destination"
        type: "http"
        url: "https://api.example.com/webhooks/github"
        method: "POST"
        headers:
          Authorization: "Bearer {{ env.API_TOKEN }}"
        timeout: 30.0
        retry:
          strategy: "exponential"
          max_retries: 3
          base_delay: 1.0
          max_delay: 60.0

  - name: "all-events-to-file"
    description: "Log all webhooks to a JSON file"
    filter: {}
    transform:
      strategy: "none"
    destinations:
      - name: "file-destination"
        type: "file"
        file_path: "./webhook-logs/events.json"

  - name: "debug-console"
    description: "Print all events to console for debugging"
    filter:
      headers:
        X-Debug: "true"
    transform:
      strategy: "none"
    destinations:
      - name: "console-destination"
        type: "console"
"""


@click.group()
@click.version_option(version=__version__, prog_name="webhook-router")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging.")
def main(verbose: bool) -> None:
    """Webhook Router — route webhooks to multiple destinations."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)


@main.command()
@click.option("--config", "-c", "config_path", default="./webhook-router.yaml", help="Path to config file.")
@click.option("--host", "-h", default=None, help="Override server host.")
@click.option("--port", "-p", type=int, default=None, help="Override server port.")
def start(config_path: str, host: str | None, port: int | None) -> None:
    """Start the webhook router server."""
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: Config file not found: {config_path}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    if host:
        config.server.host = host
    if port:
        config.server.port = port

    click.echo(f"Starting webhook router on {config.server.host}:{config.server.port}")
    click.echo(f"Loaded {len(config.routes)} route(s)")

    server = WebhookServer(config)

    async def _run() -> None:
        await server.start()

    try:
        import asyncio
        asyncio.run(_run())
    except KeyboardInterrupt:
        click.echo("\nShutting down...")


@main.command(name="validate")
@click.option("--config", "-c", "config_path", default="./webhook-router.yaml", help="Path to config file.")
def validate(config_path: str) -> None:
    """Validate webhook router configuration."""
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: Config file not found: {config_path}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Validation failed: {e}", err=True)
        sys.exit(1)

    summary = config.get_routes_summary() if hasattr(config, "get_routes_summary") else {
        "total_routes": len(config.routes),
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
            for r in config.routes
        ],
    }

    click.echo(f"Configuration valid ✓")
    click.echo(f"Routes: {summary['total_routes']}")
    for route in summary["routes"]:
        click.echo(f"  - {route['name']}: {len(route['destinations'])} destination(s)")
    click.echo(f"Server: {config.server.host}:{config.server.port}")


@main.command(name="sample-config")
@click.option("--output", "-o", "output_path", default=None, help="Write to file instead of stdout.")
def sample_config(output_path: str | None) -> None:
    """Print a sample configuration file."""
    if output_path:
        Path(output_path).write_text(SAMPLE_CONFIG, encoding="utf-8")
        click.echo(f"Sample config written to {output_path}")
    else:
        click.echo(SAMPLE_CONFIG)


@main.command(name="routes")
@click.option("--config", "-c", "config_path", default="./webhook-router.yaml", help="Path to config file.")
def routes(config_path: str) -> None:
    """Show configured routes in a readable format."""
    try:
        config = load_config(config_path)
    except FileNotFoundError:
        click.echo(f"Error: Config file not found: {config_path}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error loading config: {e}", err=True)
        sys.exit(1)

    for i, route in enumerate(config.routes, 1):
        click.echo(f"\nRoute {i}: {route.name}")
        click.echo(f"  Description: {route.description}")
        click.echo(f"  Event types: {', '.join(route.filter.event_types) or 'any'}")
        click.echo(f"  Destinations:")
        for dest in route.destinations:
            target = dest.url or dest.file_path or "console"
            click.echo(f"    - {dest.name} ({dest.type.value}) → {target}")

    click.echo(f"\nTotal routes: {len(config.routes)}")


if __name__ == "__main__":
    main()
