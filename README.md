# Webhook Router

A lightweight CLI tool for routing webhooks to multiple destinations with filtering, transformation, and retry logic.

## Features

- **Multi-destination routing** — Send each webhook to HTTP endpoints, files, or console simultaneously
- **Smart filtering** — Filter by event type, headers, or payload content (including nested keys)
- **Payload transformation** — Transform payloads using Jinja2 templates or JSON path extraction
- **Retry with backoff** — Configurable retry strategies (fixed or exponential) for failed HTTP deliveries
- **Signature verification** — HMAC-SHA256 webhook signature verification
- **Rate limiting** — Built-in token bucket rate limiter for incoming webhooks
- **YAML configuration** — Declarative, human-readable config file
- **CLI interface** — Start server, validate config, list routes, generate sample config

## Quick Start

### Installation

```bash
uv pip install webhook-router
```

Or clone and install locally:

```bash
git clone https://github.com/EdgarOrtegaRamirez/webhook-router.git
cd webhook-router
uv pip install -e .
```

### Generate a sample config

```bash
webhook-router sample-config -o webhook-router.yaml
```

### Validate your config

```bash
webhook-router validate -c webhook-router.yaml
```

### Start the server

```bash
webhook-router start -c webhook-router.yaml
```

The server listens on `0.0.0.0:8080` by default. Send webhooks to:

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -H "X-Event-Type: push" \
  -d '{"ref": "main", "action": "push"}'
```

## Configuration

### Server

```yaml
server:
  host: "0.0.0.0"      # Bind address
  port: 8080            # Port number
  log_level: "INFO"     # DEBUG, INFO, WARNING, ERROR
  cors_origins: ["*"]   # CORS allowed origins
```

### Signature Verification

```yaml
signature:
  enabled: true
  algorithm: "hmac-sha256"
  header_name: "X-Signature"
  secret_env_var: "WEBHOOK_SECRET"
```

Set the `WEBHOOK_SECRET` environment variable for HMAC verification.

### Rate Limiting

```yaml
rate_limit:
  enabled: true
  requests_per_minute: 100
  burst_size: 20
```

### Routes

Each route defines a filter, transformation, and list of destinations:

```yaml
routes:
  - name: "github-push"
    description: "Route GitHub push events"
    filter:
      event_types: ["push"]
      headers:
        X-GitHub-Event: "push"
      payload_keys:
        ref: "main"
    transform:
      strategy: "jinja2"
      template: '{"event": "{{ action }}", "repo": "{{ repository.name }}"}'
    destinations:
      - name: "api"
        type: "http"
        url: "https://api.example.com/webhooks"
        method: "POST"
        timeout: 30.0
        retry:
          strategy: "exponential"
          max_retries: 3
          base_delay: 1.0
          max_delay: 60.0
```

### Destination Types

| Type | Fields | Description |
|------|--------|-------------|
| `http` | `url`, `method`, `headers`, `timeout` | Send to an HTTP endpoint |
| `file` | `file_path` | Append to a JSON file |
| `console` | *(none)* | Log to Python logger |

### Retry Strategies

| Strategy | Behavior |
|----------|----------|
| `none` | No retries |
| `fixed` | Constant delay between retries |
| `exponential` | Delay doubles each retry (capped at `max_delay`) |

## CLI Reference

```
webhook-router <command> [options]

Commands:
  start        Start the webhook router server
  validate     Validate configuration file
  sample-config  Print or write a sample configuration
  routes       Show configured routes
  --version    Show version
  -v, --verbose  Enable verbose logging
```

## Architecture

```
Incoming Webhook
       │
       ▼
┌──────────────┐
│   Server     │  ← aiohttp HTTP server
│  (aiohttp)   │
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  Router      │  ← Match event → filter → transform → dispatch
│   Engine     │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────┐
│  Destinations                    │
│  ┌─────────┐ ┌──────┐ ┌────────┐ │
│  │  HTTP   │ │ File │ │Console │ │
│  │(retry)  │ │(JSON)│ │(log)   │ │
│  └─────────┘ └──────┘ └────────┘ │
└──────────────────────────────────┘
```

## Security

- HMAC signature verification for webhook authenticity
- Environment variables for secrets (never in config files)
- Input validation via Pydantic models
- Timeout on HTTP requests to prevent hanging
- Rate limiting to prevent abuse

## License

MIT
