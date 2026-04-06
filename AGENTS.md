# AGENTS.md - Guide for Agentic Contributors
This file is for coding agents operating in this repository.
Follow existing patterns first, then the rules below.

## 1) Repository Snapshot
- Main app: Flask monolith in `app.py`.
- Data models: SQLAlchemy models in `models.py`.
- LLM and RAG helpers: `llm.py`, `rag.py`, `vector_store.py`.
- Views/assets: `templates/`, `static/`, `static/uploads/`.
- Persistent data: `instance/` (SQLite), `chroma_db/` (Chroma DB).
- Container setup: `Dockerfile`, `docker-compose.yml`, scripts in `docker/`.
- Optional companion service: FastAPI TTS in `Servertts/app/main.py`.
- Python target: 3.11.
- Dependency files: `requirements.txt`, `Servertts/requirements.txt`.
- Never commit real secrets from `.env` files.

## 2) Build and Run Commands (Flask App)
Local setup and run:
```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS/Linux
source .venv/bin/activate
pip install -r requirements.txt
flask --app app.py run --debug --port 5000
```
Alternative app entrypoint (hardcoded port 5002 in `app.py`):
```bash
python app.py
```
Flask CLI commands defined in this repo:
```bash
flask --app app.py init-db
flask --app app.py create-admin
flask --app app.py create-user
flask --app app.py seed
```

## 3) Docker Commands
Start all services (`museo-app`, `ollama`, `ngrok`):
```bash
docker compose up -d --build
```
Stop all services:
```bash
docker compose down
```
Rebuild and recreate:
```bash
docker compose up -d --build --force-recreate
```
Service logs:
```bash
docker compose logs -f museo-app
docker compose logs -f ollama
docker compose logs -f ngrok
```

## 4) Lint, Format, and Type-Check
No committed Black/Ruff/Mypy/Isort config exists right now.
Use default behavior unless a task explicitly adds tool config.
Install:
```bash
pip install black isort ruff mypy
```
Run:
```bash
black .
isort .
ruff check .
mypy .
```

## 5) Test Commands (Pytest)
Current state: no committed `tests/` directory.
When adding tests, use `tests/test_*.py` and `pytest`.
Install test deps:
```bash
pip install pytest pytest-cov
```
Run full suite:
```bash
pytest
pytest --cov=.
```
Run a single test file:
```bash
pytest tests/test_example.py
```
Run a single test function:
```bash
pytest tests/test_example.py::test_specific_behavior
```
Run filtered tests:
```bash
pytest -k "chat and not slow"
```

## 6) Code Style and Engineering Rules
Imports:
- Order imports as: standard library, third-party, local modules.
- Keep one blank line between import groups.
- Prefer top-level imports.
- Use function-local imports only for lazy/optional deps.

Formatting:
- Keep Black-compatible style (88-char target).
- Use 4 spaces, never tabs.
- Keep functions focused; extract helpers for long blocks.
- Preserve local style in touched files.

Types:
- Add type hints for new/changed public functions.
- Prefer built-in generics (`list[str]`, `dict[str, Any]`).
- Prefer `X | None` over `Optional[X]` in new code.

Naming:
- Variables/functions/modules: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.

Flask conventions:
- Use explicit method decorators (`@app.get`, `@app.post`).
- Validate request data early and fail fast.
- Use `abort(403)` / `abort(404)` for page routes when appropriate.
- Use `jsonify(...), status_code` for API responses.

Database conventions:
- Use existing SQLAlchemy ORM/session patterns.
- Commit after grouped writes; roll back on failed validation/upload flows.
- Keep schema update logic centralized (see `ensure_schema_updates()`).
- Never build SQL from unsanitized user input.

Error handling:
- Catch narrow exceptions where practical.
- Convert network/IO/LLM boundary failures into safe user-facing errors.
- Keep API error payloads machine-readable and consistent.

Security and file handling:
- Sanitize IDs with existing helper and regex patterns.
- Use `secure_filename` for uploads.
- Enforce extension allowlists (`ALLOWED_DOCS`, `ALLOWED_AUDIO`, `ALLOWED_IMAGES`).
- Keep auth checks explicit (`login_required`, admin guards, API keys).

Logging:
- Prefer concise operational logs.
- Avoid noisy logs in hot paths.
- Do not log credentials, API keys, or sensitive payloads.

## 7) Cursor and Copilot Rules
Checked for repository-level instruction files:
- `.cursorrules`
- `.cursor/rules/`
- `.github/copilot-instructions.md`
Current state: none of these files exist in this repo.
If added later, treat them as higher-priority policy and merge into this guide.

## 8) Agent Checklist Before Finishing
- Read all touched files before editing.
- Keep changes scoped; avoid unrelated refactors.
- Run relevant format/lint/test commands when possible.
- Update docs when behavior or commands change.
- Add targeted tests for changed behavior when scope allows.
