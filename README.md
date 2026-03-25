# HTTP Parrots

Every HTTP status code, explained by parrots.

A fun, interactive reference for HTTP status codes featuring cartoon parrot illustrations, detailed explanations, code examples, and developer tools.

## Features

**Browse** - Gallery of 72 HTTP status codes with search, category filtering, and a "parrot of the day"

**Learn** - Each status code has:
- Description and history with clickable RFC links
- Real-world examples ("When would I see this?")
- Code snippets in Python, Node.js, and Go
- Example HTTP request/response exchange
- Typical response headers

**Interactive tools**
- **Quiz** (`/quiz`) - Guess the status code from the parrot image
- **Flowchart** (`/flowchart`) - Interactive decision tree to pick the right status code
- **HTTP Tester** (`/tester`) - Enter a URL and see what status code it returns
- **Cheat Sheet** (`/cheatsheet`) - Printable single-page reference

**API** - Programmatic access to all data:
- `GET /<code>` with `Accept: application/json` returns JSON
- `GET /<code>.jpg` returns the parrot image directly
- `GET /return/<code>` returns an actual HTTP response with that status code
- `GET /api/check-url?url=<url>` checks what status code a URL returns
- `GET /random` redirects to a random status code

Full API documentation at `/api-docs`, including Slack and Discord bot integration guides.

## Keyboard shortcuts

| Key | Page | Action |
|-----|------|--------|
| `/` | Homepage | Focus search |
| `Escape` | Homepage | Blur search |
| Arrow keys | Homepage | Navigate the grid |
| `Enter` | Homepage | Open focused card |
| `←` `→` | Detail page | Previous / next status code |
| `1`-`4` | Quiz | Select answer |
| `Enter` | Quiz | Next question |

## CLI

Look up HTTP status codes from the terminal:

```bash
./cli/httpparrot 404        # Look up a code
./cli/httpparrot 4xx        # List a category
./cli/httpparrot all        # List all codes
./cli/httpparrot teapot     # Search by keyword
./cli/httpparrot redirect   # Search descriptions
```

No dependencies required — just Python 3.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app index run
```

## Running tests

```bash
pip install -r requirements-dev.txt
python -m pytest test_app.py test_cli.py -v
```

## Tech stack

- Python 3 / Flask 3.1
- Jinja2 templates with template inheritance
- Custom CSS (no framework dependencies)
- Vanilla JavaScript (no external dependencies)

## Security

- SSRF protection with IP validation and DNS rebinding prevention
- Content Security Policy with per-request nonces (no unsafe-inline)
- HSTS, X-Frame-Options, and other security headers
- XSS-safe templates (Jinja2 auto-escaping, safe DOM APIs in JavaScript)
- Rate limiting on outbound request endpoints
- No external JavaScript dependencies

## Deployment

The included `Procfile` runs the app with gunicorn:

```
web: gunicorn index:app --preload --workers 2
```

Set the `SECRET_KEY` environment variable in production.

## License

See [LICENSE](LICENSE).
