# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities to the repository maintainers via GitHub Issues with the "security" label.

## Security Features

- HMAC signature verification for webhook authenticity
- Secrets via environment variables only (never in config files)
- Input validation via Pydantic models
- HTTP request timeouts to prevent hanging connections
- Rate limiting to prevent abuse
- No shell execution of user input

## Known Limitations

- CORS is configurable but defaults to allowing all origins
- File destinations use append mode — no rotation (use external log rotation)
- No TLS termination (use a reverse proxy like nginx for HTTPS)
