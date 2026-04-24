# AGENTS.md - Guide for Coding Agents
This guide is for agentic contributors working in `E:\ProyectoUniversidad\Museo\InformacionMuseo`.
Read files before editing, preserve existing patterns, and keep diffs tight.

## Repository Snapshot
- Main Flask app: `app.py`.
- Models: `models.py` with Flask-SQLAlchemy.
- LLM/RAG helpers: `llm.py`, `rag.py`, `vector_store.py`.
- TTS sidecar: FastAPI app in `Servertts/app/main.py`.
- Templates: `templates/`.
- Static assets/uploads: `static/`, `static/uploads/`.
- Local persistence: `instance/` (SQLite), `chroma_db/` (Chroma).
- Containers: `Dockerfile`, `docker-compose.yml`, `docker/`.
- Python dependency files: `requirements.txt`, `Servertts/requirements.txt`.

## Environment and Secrets
- Copy `.env.example` to `.env` before local or Docker runs.
- Required values usually include `SECRET_KEY`, `MUSEO_TTS_SHARED_KEY`, `TTS_API_KEY`, and admin credentials.
- Do not hardcode or commit real keys, tokens, DB files, or private uploads.
- Treat `.env`, `instance/`, `chroma_db/`, `ollama/`, `Servertts/cache_audio/`, and `Servertts/debug_frames/` as local state.

## Run Commands
Flask CLI server:
```bash
flask --app app.py run --debug --port 5000
```
Direct Flask entrypoint:
```bash
python app.py
```
`python app.py` runs the debug server on port `5002`.
TTS service:
```bash
uvicorn Servertts.app.main:app --reload --host 0.0.0.0 --port 8010
```

## Flask CLI Commands
Defined in `app.py`; prefer them over ad hoc scripts:
```bash
flask --app app.py init-db
flask --app app.py create-admin
flask --app app.py create-user
flask --app app.py seed
flask --app app.py reindex-all
```

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

## Build, Lint, and Format
There is no committed `pyproject.toml`, `ruff.toml`, `mypy.ini`, `setup.cfg`, `tox.ini`, or `pytest.ini`.
No repo-wide formatter/linter is enforced, so avoid sweeping cleanup.
Install optional developer tools:
```bash
pip install black isort ruff mypy
```
Recommended checks for touched files:
```bash
black app.py models.py llm.py rag.py vector_store.py Servertts/app/main.py
isort app.py models.py llm.py rag.py vector_store.py Servertts/app/main.py
ruff check app.py models.py llm.py rag.py vector_store.py Servertts/app/main.py
mypy app.py models.py llm.py rag.py vector_store.py Servertts/app/main.py
```
If you changed one file, prefer running tools on that file only.

## Test Commands
There is currently no committed `tests/` directory and no established automated suite.
If you add tests, use `pytest` and place them under `tests/` with names like `tests/test_*.py`.
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
Run a subset by expression:
```bash
pytest -k "chat and not slow"
```
If no automated tests exist for your change, say so and perform focused manual verification.

## Code Style
Imports:
- Order imports as standard library, third-party, then local modules.
- Separate groups with one blank line.
- Avoid wildcard imports.
- Keep imports at module top level unless a local import is needed for optional or expensive dependencies.
Formatting:
- Use 4 spaces and keep code Black-compatible near 88 columns unless the surrounding file clearly differs.
- Prefer small helpers over deeply nested conditionals.
- Match surrounding quote style and spacing in older files.
- Do not reformat unrelated Spanish literals, templates, or large text blocks.
Types:
- Add type hints for new or changed public functions.
- Prefer built-in generics like `list[str]` and `dict[str, Any]`.
- Prefer `X | None` over `Optional[X]` in modern-typed code.
- Keep JSON, template, and API payload shapes stable.
Naming:
- Functions, variables, and modules: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- Use descriptive route/helper names such as `create_user`, `edit_species`, or `chat_stream`.
- Reuse established project vocabulary, even when names or UI copy are in Spanish.

## Framework, DB, and Persistence Conventions
- Prefer explicit Flask/FastAPI decorators such as `@app.get`, `@app.post`, and `@app.cli.command`.
- Validate request data early and fail fast on invalid input.
- Use `abort(403)` and `abort(404)` for page routes when appropriate.
- Return stable JSON payloads with `jsonify` or `JSONResponse`.
- Keep auth checks explicit with `login_required`, admin guards, and shared API key validation.
- Reuse helpers like `sanitize_id`, `ext_of`, payload builders, and `ensure_schema_updates()` before adding new logic.
- Use `db.session` consistently and group related writes into one commit when practical.
- Do not build SQL from unsanitized user input.
- Preserve species IDs, QR IDs, and existing relationships when editing records.
- When changing ingestion/retrieval logic, consider both SQLite data and Chroma vector state.

## Error Handling and External Calls
- Catch narrow exceptions where practical; avoid broad `except Exception` unless the fallback is deliberate.
- Wrap network, LLM, and TTS failures with clear user-safe messages.
- Use explicit HTTP timeouts; this codebase already does so in `requests` calls.
- Do not silently swallow exceptions unless the action is truly optional.
- Sanitize uploaded filenames with `secure_filename` and enforce existing allowlists such as `ALLOWED_DOCS`, `ALLOWED_AUDIO`, and `ALLOWED_IMAGES`.
- Avoid logging secrets, tokens, or large third-party payloads.

## Editing and Verification Expectations
- Read touched files first and follow local patterns.
- Keep changes tightly scoped; avoid unrelated refactors.
- Prefer extending existing helpers over duplicating logic.
- Preserve Spanish user-facing copy unless the task explicitly asks for wording changes.
- For route changes, verify both success and failure paths.
- For DB changes, verify commands like `init-db`, `create-admin`, or `seed` still make sense.
- For LLM/RAG changes, verify degraded behavior when Ollama or embeddings are unavailable.
- For TTS changes, verify behavior when `servertts` or its credentials are missing.
- If you cannot run automated checks, do the narrowest useful manual verification and report what you did not verify.

## Cursor and Copilot Rules
Checked repository-level instruction sources: `.cursorrules`, `.cursor/rules/`, `.github/copilot-instructions.md`.
Current state: none of these files exist in this repository.
If any are added later, treat them as higher-priority instructions and merge them with this guide.

## Handoff Checklist
- Mention every file you changed.
- Mention the commands you ran to verify the change.
- Call out missing env vars, unverified paths, or skipped checks.
- State clearly when no automated tests were available.
