# CLAUDE.md

## Project

HTTP Parrots -- a Flask web app that explains HTTP status codes with illustrated parrot images. Includes a quiz (adaptive difficulty), daily/weekly challenges, scenario practice, debug exercises, confusion pair lessons, guided learning paths (with completion certificates), spaced repetition review, XP/badge gamification (29 feathers), command palette, customizable profiles, flowchart, URL tester, response playground, fault simulator, webhook inspector, cURL importer (with Playground integration), redirect tracer, security audit, CORS checker, header explainer, Parrotdex, cheat sheet, and API.

## Development

- Python 3.11, Flask, virtualenv at `.venv`
- Run locally: `.venv/bin/python index.py` (serves on http://127.0.0.1:5000)
- Flask is NOT in debug mode -- restart the server after changing Python files or templates
- Tests: `.venv/bin/python -m pytest`
- 1766 tests across test_app.py (1748) and test_cli.py (18)
- Coverage: 97%+ of index.py

## Architecture

- `index.py` -- main Flask app with all routes (~2137 lines)
- `status_descriptions.py` -- STATUS_INFO dict with descriptions, history, meaning for each code
- `status_extra.py` -- STATUS_EXTRA dict with examples, ELI5 text (all 72 codes), case studies (135 entries across 70 codes), 96 common mistakes (48 codes), 15 "When NOT to use" sections, code snippets in 5 languages (Python, Node.js, Go, Java, Rust)
- `http_examples.py` -- HTTP_EXAMPLES dict with request/response text for each code
- `scenarios.py` -- 56 practice scenarios (including 5 security category) with difficulty, options, and explanations
- `debug_exercises.py` -- 36 debug exercises with broken HTTP exchanges and bugs to find
- `confusion_pairs.py` -- 15 confusion pair lesson definitions with slugs, categories, and content
- `learning_paths.py` -- 3 guided learning paths (http-foundations, error-whisperer, redirect-master)
- `templates/` -- 31 Jinja2 templates (base.html has XP system, ranks, and badge JS)
- `static/` -- parrot images (72 codes), CSS (design-token-based system), and static assets
- `cli/` -- standalone CLI tool (no Flask dependency)

## Key data modules

When adding new content:
- New scenarios go in `scenarios.py` (each needs id, category, difficulty, description, correct, options, explanations)
- New debug exercises go in `debug_exercises.py` (each needs id, difficulty, category, title, description, request, response, bugs, related_codes)
- New confusion pairs go in `confusion_pairs.py` (update CONFUSION_PAIRS list and ensure slug, codes, category, content fields)
- New learning paths go in `learning_paths.py` (step types: visit, practice, debug, quiz, learn)
- ELI5 entries go in `status_extra.py` under the `eli5` key for each code (all 72 currently covered)
- Case studies go in `status_extra.py` under the `case_studies` key (135 entries across 70 codes)
- Common mistakes go in `status_extra.py` under the `common_mistakes` key (96 entries across 48 codes)
- "When NOT to use" entries go in `status_extra.py` under the `dont_use_when` key (15 codes currently covered)

## Gamification

All XP, badges, streaks, daily login rewards, avatar, accent color, and Parrotdex state are stored client-side in localStorage (keys prefixed `httpparrot_`). The XP system, rank definitions (10 ranks), and badge definitions (29 "Feathers": 23 base + 6 meta) live in `templates/base.html` in a `<script>` block so they are available on every page.

Badge categories:
- **23 base feathers**: First Flight, Quiz Whiz, Perfect 10, Streak Starter, On Fire, Centurion, Wing Commander, Completionist, Error Expert, Server Sage, Egg Hunter, Scholar, Night Owl, Speed Demon, Frozen Solid, Memory Master, Parrot Petter, Photographic Memory, Loyal Parrot, Theme Master, Explorer 10, Explorer 25, Explorer 50
- **6 meta feathers** (awarded for combinations of other badges): Explorer, Polyglot, Streak Lord, Triple Threat, Full Spectrum, Parrot Polymath
- **Meta-feather unlock animations**: golden confetti burst and screen shake

## Design system

CSS uses a full design-token system. Tokens cover spacing, color palettes (both dark and light themes), typography scale, elevation/shadow levels, and border radii. Mobile layouts are polished down to 320px-375px. Light theme has complete coverage via `prefers-color-scheme: light`.

## Rules

- Always update tests when making code changes
- Always update documentation (README, docstrings, etc.) when changing behavior or adding features
- When adding new elements make sure the design takes inspiration from Soundtrap
- All route handler functions must have docstrings
- All outbound-request endpoints must use resolve_and_validate() for SSRF protection and is_rate_limited() for rate limiting
- Security-sensitive headers must be stripped from echo/webhook responses (see _ECHO_STRIP_HEADERS, _WEBHOOK_STRIP_HEADERS)
