# AGENTS.md - Guide for Coding Agents
This guide is for agentic contributors working in `E:\ProyectoUniversidad\Museo\InformacionMuseo`.
Read touched files first, follow existing patterns, and keep changes tightly scoped.

## Repository Overview
- Main web app: Flask app in `app.py`.
- ORM models: `models.py` with Flask-SQLAlchemy.
- LLM/RAG helpers: `llm.py`, `rag.py`, `vector_store.py`.
- TTS companion service: FastAPI app in `Servertts/app/main.py`.
- Templates/assets: `templates/`, `static/`, `static/uploads/`.
- Local data: `instance/` for SQLite, `chroma_db/` for Chroma.
- Containers: root `Dockerfile`, `docker-compose.yml`, scripts in `docker/`.
- Python target in containers: 3.11.
- Dependency files: `requirements.txt`, `Servertts/requirements.txt`.

## Setup and Run
Main Flask app setup:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```
Run the main app:
```bash
flask --app app.py run --debug --port 5000
```
Alternative direct entrypoint:
```bash
python app.py
```
`python app.py` runs the hardcoded debug server on port `5002`.
TTS FastAPI service:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r Servertts/requirements.txt
uvicorn Servertts.app.main:app --reload --host 0.0.0.0 --port 8010
```

## Flask CLI Commands
Defined in `app.py`:
```bash
flask --app app.py init-db
flask --app app.py create-admin
flask --app app.py create-user
flask --app app.py seed
flask --app app.py reindex-all
```
Use these instead of ad hoc DB scripts.

## Docker Commands
```bash
docker compose up -d --build
docker compose down
docker compose up -d --build --force-recreate
docker compose logs -f museo-app
docker compose logs -f servertts
docker compose logs -f ollama
docker compose logs -f ngrok
docker compose logs -f ngrok-tts
```

## Lint, Format, and Type Checking
No committed `pyproject.toml`, `ruff.toml`, `mypy.ini`, `setup.cfg`, or `pytest.ini` exists.
Tooling is not enforced repo-wide, so avoid mass cleanup in unrelated files.
Recommended install:
```bash
pip install black isort ruff mypy
```
Recommended commands:
```bash
black .
isort .
ruff check .
mypy .
```
Prefer formatting only the files you touched.

## Test Commands
There is currently no committed `tests/` directory and no existing automated suite.
If you add tests, use `pytest` and name files `tests/test_*.py`.
Install test tools:
```bash
pip install pytest pytest-cov
```
Run all tests:
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
Run a single test class:
```bash
pytest tests/test_example.py::TestChatFlow
```
Run matching tests only:
```bash
pytest -k "chat and not slow"
```
If no tests exist for your change, state that clearly in the handoff.

## Code Style
Imports:
- Order imports as standard library, third-party, then local modules.
- Separate groups with one blank line.
- Avoid wildcard imports.
- Keep imports at module top level unless a local import is needed for optional or expensive dependencies.

Formatting:
- Use 4 spaces.
- Keep code Black-compatible and roughly 88 columns unless local style differs.
- Prefer small helpers over deeply nested branches.
- Match the surrounding file's quote style and spacing when editing older code.
- Avoid reformatting unrelated Spanish text blocks, templates, or large literals.

Types:
- Add type hints for new or changed public functions.
- Prefer built-in generics such as `list[str]` and `dict[str, Any]`.
- Prefer `X | None` over `Optional[X]` in modern-typed files.
- Keep JSON-like return shapes stable for templates and API callers.

Naming:
- Functions, variables, modules: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Use descriptive route handler names like `create_user`, `edit_species`, or `chat_stream`.
- Reuse established project terms even when they are in Spanish.

## Framework and Persistence Conventions
- Prefer explicit Flask/FastAPI decorators such as `@app.get` and `@app.post`.
- Validate request data early and fail fast on invalid input.
- For page routes, use `abort(403)` and `abort(404)` where appropriate.
- For JSON endpoints, return stable payloads with `jsonify` or `JSONResponse`.
- Keep auth checks explicit with `login_required`, admin guards, and API-key validation.
- Reuse helpers like `sanitize_id`, `ext_of`, and existing payload builders.
- Use `db.session` consistently, group related writes, and commit once.
- Keep schema-fix logic centralized around `ensure_schema_updates()`.
- Do not build SQL from unsanitized user input.
- Preserve existing species IDs and QR relationships when editing records.

## Error Handling, Security, and External Calls
- Catch narrow exceptions where practical.
- Wrap network/LLM/TTS failures with safe, useful messages.
- Use explicit HTTP timeouts; existing `requests` code already does this.
- Do not silently swallow exceptions unless the action is truly optional.
- Use `secure_filename` for uploads.
- Enforce existing allowlists such as `ALLOWED_DOCS`, `ALLOWED_AUDIO`, and `ALLOWED_IMAGES`.
- Sanitize user-provided identifiers with existing regex and helper patterns.
- Never commit real `.env` values, API keys, or generated private data.
- Do not log credentials, tokens, or large third-party responses containing sensitive data.

## Testing Expectations for Agents
- Prefer focused tests for parsing, validation, utility, or API behavior.
- If you cannot add automated tests, perform the narrowest useful manual verification.
- When changing routes, verify both success and failure paths.
- When changing DB logic, verify startup commands still work.
- When changing TTS or LLM integration, verify behavior degrades safely when services are unavailable.

## Cursor and Copilot Rules
Checked these repository-level instruction sources: `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`.
Current state: none of these files exist in this repository.
If they are added later, treat them as higher-priority instructions and merge them with this guide.

## Finish Checklist
- Read all touched files before editing.
- Keep diffs focused; avoid unrelated refactors.
- Prefer existing helpers over duplicate logic.
- Run relevant format, lint, and test commands when practical.
- Update docs when behavior, commands, or setup change.
- Call out missing env vars, unverified paths, and absent tests in the final handoff.
