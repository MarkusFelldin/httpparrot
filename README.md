# HTTP Parrots

Every HTTP status code, explained by parrots.

A fun, interactive reference for HTTP status codes featuring cartoon parrot illustrations, detailed explanations, code examples, and developer tools.

## Features

**Browse** - Gallery of 72 HTTP status codes with search, category filtering, and an enhanced "Parrot of the Day" section with fun facts and sharing

**Learn** - Each status code has:
- Description and history with clickable RFC links
- Real-world examples ("When would I see this?")
- Code snippets in Python, Node.js, and Go
- Example HTTP request/response exchange with syntax highlighting
- Typical response headers
- "Commonly confused with" links to related status codes
- Copy-as-curl button for the `/return/<code>` endpoint
- **ELI5 mode** - Toggle "Simple mode" for fun, plain-language analogies (18 common codes)
- **Share buttons** - Native Share API, Twitter/X, Slack, Discord, copy link
- **Embed codes** - Copy HTML, Markdown, or direct image URL for any parrot

**Interactive tools**
- **Quiz** (`/quiz`) - Guess the status code from the parrot image
- **Daily Challenge** (`/daily`) - Wordle-style daily quiz with streak tracking and shareable results
- **Scenario Practice** (`/practice`) - 25 real-world API scenarios sorted by difficulty (beginner/intermediate/expert)
- **Flowchart** (`/flowchart`) - Interactive decision tree to pick the right status code
- **Compare** (`/compare`) - Side-by-side comparison with visual diff, presets (401 vs 403, etc.), and swap button
- **HTTP Tester** (`/tester`) - Enter a URL and see what status code it returns
- **Response Playground** (`/playground`) - Build custom HTTP responses with live preview and presets
- **Header Explainer** (`/headers`) - Paste HTTP headers for instant color-coded explanations
- **CORS Checker** (`/cors-checker`) - Test CORS policies for any URL
- **Cheat Sheet** (`/cheatsheet`) - Printable single-page reference with parrot thumbnails
- **Parrotdex** (`/collection`) - Gamified collection tracker for visited status codes

**Interactive details**
- Category-themed hover effects: 1xx pulses, 2xx glows, 3xx slides sideways, 4xx shakes, 5xx glitches
- Speech bubbles with typewriter effect — each parrot has a witty one-liner
- Easter eggs on specific cards: 204 fades to nothing, 418 has steam, 429 spawns tiny parrots, 508 spins
- Konami code party mode on the homepage
- Aurora gradient background with animated floating orbs
- Glassmorphism card hover effects with category-colored inner glow
- CSS scroll-driven animations with diagonal cascade card entry
- Tactile micro-interactions (spring-physics easing, bounce, press states)

**API** - Programmatic access to all data:
- `GET /<code>` with `Accept: application/json` returns JSON
- `GET /<code>.jpg` returns the parrot image directly
- `GET /return/<code>` returns an actual HTTP response with that status code
- `GET /api/check-url?url=<url>` checks what status code a URL returns
- `GET /api/diff?code1=X&code2=Y` compares two status codes
- `GET /api/search?q=keyword` searches codes by name, description, or number
- `POST /api/mock-response` creates custom HTTP responses
- `GET /echo` echoes requests back (all methods, `?format=pretty|curl`)
- `GET /feed.xml` RSS feed with daily parrot
- `GET /random` redirects to a random status code

Full API documentation at `/api-docs`, including Slack and Discord bot integration guides.

**Accessibility**
- WCAG AA color contrast compliance
- Full ARIA labels, roles, and live regions across all pages
- Keyboard navigable with visible focus indicators
- Screen reader support for quiz scores, streaks, and dynamic content
- `prefers-reduced-motion` support (disables all animations)
- `prefers-color-scheme: light` theme
- Print stylesheet for all pages (optimized for cheat sheet)
- Responsive hamburger menu for mobile navigation

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
- Custom CSS with glassmorphism, scroll-driven animations, light/dark themes (no framework dependencies)
- Vanilla JavaScript (no external dependencies)
- 400+ automated tests with 97%+ code coverage

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
