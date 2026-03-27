# CLAUDE.md

## Project

HTTP Parrots -- a Flask web app that explains HTTP status codes with illustrated parrot images. Includes a quiz, daily/weekly challenges, scenario practice, debug exercises, confusion pair lessons, guided learning paths, spaced repetition review, XP/badge gamification, flowchart, URL tester, response playground, fault simulator, webhook inspector, cURL importer, redirect tracer, security audit, CORS checker, header explainer, cheat sheet, and API.

## Development

- Python 3.11, Flask, virtualenv at `.venv`
- Run locally: `.venv/bin/python index.py` (serves on http://127.0.0.1:5000)
- Flask is NOT in debug mode -- restart the server after changing Python files or templates
- Tests: `.venv/bin/python -m pytest`
- 1142 tests across test_app.py (1124) and test_cli.py (18)

## Architecture

- `index.py` -- main Flask app with all routes (~2000 lines)
- `status_descriptions.py` -- STATUS_INFO dict with descriptions, history, meaning for each code
- `status_extra.py` -- STATUS_EXTRA dict with examples, ELI5 text, code snippets
- `http_examples.py` -- HTTP_EXAMPLES dict with request/response text for each code
- `scenarios.py` -- 51 practice scenarios with category, difficulty, options, and explanations
- `debug_exercises.py` -- 31 debug exercises with broken HTTP exchanges and bugs to find
- `confusion_pairs.py` -- 15 confusion pair lesson definitions with slugs, categories, and content
- `learning_paths.py` -- 3 guided learning paths (http-foundations, error-whisperer, redirect-master)
- `templates/` -- 31 Jinja2 templates (base.html has XP system, ranks, and badge JS)
- `static/` -- parrot images (72 codes), CSS, and static assets
- `cli/` -- standalone CLI tool (no Flask dependency)

## Key data modules

When adding new content:
- New scenarios go in `scenarios.py` (each needs id, category, difficulty, description, correct, options, explanations)
- New debug exercises go in `debug_exercises.py` (each needs id, difficulty, category, title, description, request, response, bugs, related_codes)
- New confusion pairs go in `confusion_pairs.py` (update CONFUSION_PAIRS list and ensure slug, codes, category, content fields)
- New learning paths go in `learning_paths.py` (step types: visit, practice, debug, quiz, learn)

## Gamification

All XP, badges, streaks, and Parrotdex state are stored client-side in localStorage (keys prefixed `httpparrot_`). The XP system, rank definitions (10 ranks), and badge definitions (16 "Feathers") live in `templates/base.html` in a `<script>` block so they are available on every page.

## Rules

- Always update tests when making code changes
- Always update documentation (README, docstrings, etc.) when changing behavior or adding features
- When adding new elements make sure the design takes inspiration from Soundtrap
- All route handler functions must have docstrings
- All outbound-request endpoints must use resolve_and_validate() for SSRF protection and is_rate_limited() for rate limiting
- Security-sensitive headers must be stripped from echo/webhook responses (see _ECHO_STRIP_HEADERS, _WEBHOOK_STRIP_HEADERS)
