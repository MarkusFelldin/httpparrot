# CLAUDE.md

## Project

HTTP Parrots — a Flask web app that explains HTTP status codes with illustrated parrot images. Includes a quiz, flowchart, URL tester, cheat sheet, and API.

## Development

- Python 3.11, Flask, virtualenv at `.venv`
- Run locally: `.venv/bin/python index.py` (serves on http://127.0.0.1:5000)
- Flask is NOT in debug mode — restart the server after changing Python files or templates
- Tests: `.venv/bin/python -m pytest`

## Rules

- Always update tests when making code changes
- Always update documentation (README, docstrings, etc.) when changing behavior or adding features
- When adding new elements make sure the design takes inspiration from Soundtrap
