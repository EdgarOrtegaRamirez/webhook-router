# Webhook Router

## For AI Agents

This project is a lightweight CLI tool for routing webhooks to multiple destinations.

### Project Structure

```
webhook-router/
├── src/webhook_router/
│   ├── __init__.py       # Package init, version
│   ├── models.py         # Pydantic models (Config, Route, Destination, etc.)
│   ├── config.py         # YAML config loader
│   ├── router.py         # RouterEngine — matches events to routes
│   ├── http_engine.py    # HTTP delivery with retry
│   ├── file_engine.py    # File and console delivery
│   ├── server.py         # aiohttp webhook server
│   └── cli.py            # Click CLI (start, validate, sample-config, routes)
├── tests/
│   ├── test_models.py    # Model validation tests
│   ├── test_config.py    # Config loading tests
│   ├── test_engine.py    # Router engine tests
│   └── test_cli.py       # CLI command tests
├── webhook-router.yaml   # Sample config
├── pyproject.toml        # Project config (uv/hatch)
├── .gitignore
├── README.md
├── LICENSE
└── AGENTS.md
```

### Key Dependencies

- `click` — CLI framework
- `pydantic` — Data validation
- `pyyaml` — YAML config parsing
- `aiohttp` — Async HTTP server and client
- `jinja2` — Template transformation
- `cryptography` — Not directly used (pydantic handles HMAC)

### Running Tests

```bash
uv pip install -e ".[dev]"
uv run pytest tests/ -v
```

### Building

```bash
uv build
```

### Adding a New Destination Type

1. Add new enum value to `DestinationType` in `models.py`
2. Create a new `deliver_*` async function in a new engine module
3. Update the `_send_to_destination` method in `router.py` to handle the new type

### Adding a New Filter Type

1. Add field to `FilterConfig` in `models.py`
2. Update the `matches` method in `FilterConfig` to handle the new field

### Adding a New Transform Strategy

1. Add enum value to `TransformStrategy` in `models.py`
2. Add a new `_apply_*` method in `TransformConfig`
3. Update `transform` method to dispatch to the new strategy
