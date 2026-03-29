# AGENTS.md – Guidelines for the InformacionMuseo Repository

---

## 📦 Project Overview
- **Language:** Python 3.11
- **Framework:** Flask (>=3.0)
- **Database:** SQLite via Flask‑SQLAlchemy
- **LLM/Embeddings:** Ollama (qwen3.5:4b) + **chromadb**
- **Containerisation:** Docker Compose (app, ollama, ngrok)
- **Environment:** `.env` (see `.env.example`)

---

## 🛠️ Build / Run Commands
| Goal | Command | Description |
|------|---------|-------------|
| **Run locally (development)** | `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && flask run` | Uses the built‑in Flask dev server (default port 5000). |
| **Start with Docker** | `docker compose up -d --build` | Brings up `museo‑app`, `ollama` and `ngrok`. |
| **Stop Docker stack** | `docker compose down` | Stops and removes containers. |
| **Recreate containers** | `docker compose up -d --build --force-recreate` | Useful after dependency changes. |
| **View logs** | `docker compose logs -f <service>` | Replace `<service>` with `museo-app`, `ollama` or `ngrok`. |
| **Run migrations (if added)** | `flask db upgrade` | Placeholder – add Alembic/Flask‑Migrate as needed. |

---

## 📋 Linting & Formatting
- **Formatter:** `black` (auto‑format)
- **Static type checker:** `mypy --strict`
- **Linter:** `ruff` (or `flake8` if preferred)
- **Import order:** `isort` – groups: standard, third‑party, local.

```bash
# Install dev tools (add to requirements-dev.txt if you like)
python -m pip install black ruff isort mypy
```

### Quick lint / format commands
```bash
# Format all Python files
black .
# Sort imports
isort .
# Run linter
ruff .
# Type‑check
mypy . --strict
```

---

## ✅ Testing
The repository does not ship tests yet, but the recommended stack is **pytest** with **pytest‑cov**. Add a `tests/` directory and name files `test_*.py`.

### Install test deps
```bash
python -m pip install pytest pytest-cov
```

### Run the full suite
```bash
pytest --cov=.
```

### Run a single test (by name or file)
```bash
# By test function name (partial match)
pytest -k my_feature

# By file path
pytest tests/test_my_feature.py
```

---

## 🧩 Code‑Style Guidelines
### 1️⃣ Imports
```python
# 1️⃣ Standard library
import os
import re

# 2️⃣ Third‑party
import flask
import requests
from qrcode import QRCode

# 3️⃣ Local application imports
from .models import User, Species
from .utils import sanitize_id
```
- One blank line between groups.
- Alphabetical within each group.
- Use absolute imports for project modules.

### 2️⃣ Formatting
- **Line length:** 88 characters (compatible with Black).
- **Trailing commas** on multi‑line collections.
- **Quote style:** single quotes `'` for strings, double quotes `"` only when the string contains a single quote.
- End files with a single newline.

### 3️⃣ Types & Annotations
- All public functions / methods must have **type hints** for parameters and return values.
- Use `typing` imports (`List`, `Dict`, `Optional`, `Union`, `Literal`, `TypedDict`).
- Prefer `|` syntax for Union (Python 3.10+).

```python
def clamp_int(raw: Any, min_value: int, max_value: int, default: int) -> int:
    ...
```

### 4️⃣ Naming Conventions
| Element | Convention |
|---------|-------------|
| Modules / packages | `snake_case` |
| Files | `snake_case.py` |
| Classes | `PascalCase` |
| Functions / methods | `snake_case` |
| Variables | `snake_case` |
| Constants | `UPPER_SNAKE_CASE` |
| Private/internal | prefix with `_` |

### 5️⃣ Docstrings
- **Google style** (or NumPy – be consistent).
- Every public function / class gets a docstring.
- One‑line summary, blank line, then description/args/returns.
```python
def sanitize_id(raw: str) -> str:
    """Normalize a user‑provided identifier.

    Args:
        raw: Raw identifier string from the request.

    Returns:
        A lower‑cased, stripped string containing only ``a‑z``, ``0‑9``, ``-`` and ``_``.
    """
``` 

### 6️⃣ Error Handling
- Raise **custom exceptions** (subclass `Exception`) for domain errors.
- Use `try/except` only around code that can realistically fail (IO, external API calls).
- Convert external exceptions to internal ones before propagating.
- Return Flask error responses with appropriate HTTP status codes, e.g. `abort(400, "Invalid PDF")`.

### 7️⃣ Logging
- Use `import logging` and configure a module‑level logger: `log = logging.getLogger(__name__)`.
- Log at appropriate levels (`debug`, `info`, `warning`, `error`).
- Never log secrets or full request bodies.

### 8️⃣ Security
- Validate all user‑provided filenames with `secure_filename`.
- Enforce whitelist of allowed extensions (`ALLOWED_DOCS`, `ALLOWED_IMAGES`).
- Use prepared statements / ORM query parameters – never concatenate raw strings into SQL.
- Load secrets from environment variables via `python-dotenv`.

---

## 📂 Directory Layout (recommended)
```
.
├─ app.py                     # Flask entry point
├─ models.py                  # SQLAlchemy models
├─ rag.py                     # Retrieval‑augmented generation helpers
├─ llm.py                     # LLM client wrapper
├─ vector_store.py            # ChromaDB wrapper
├─ static/                    # Public assets (uploads, images, etc.)
├─ templates/                 # Jinja2 HTML templates
├─ tests/                     # Pytest suite (create if missing)
│   └─ test_*.py
├─ docker/                    # Docker helper scripts
├─ .env.example               # Example env file
├─ requirements.txt           # Production deps
├─ requirements-dev.txt       # Dev‑only deps (optional)
└─ AGENTS.md                  # THIS FILE
```

---

## 📜 Cursor / Copilot Rules (if present)
- No `.cursor` or `.cursorrules` directories were found.
- No `Copilot` instruction file (`.github/copilot‑instructions.md`) exists.
- If these files are added later, merge their contents into the relevant sections above.

---

## 📚 Helpful References
- **Flask Docs:** https://flask.palletsprojects.com/
- **Black Formatter:** https://black.readthedocs.io/
- **Ruff Linter:** https://ruff.rs/
- **Pytest Docs:** https://docs.pytest.org/
- **Mypy:** https://mypy.readthedocs.io/
- **Isort:** https://pycqa.github.io/isort/
- **Ollama API:** https://github.com/jmorganca/ollama/blob/main/docs/api.md

---

*End of AGENTS.md*