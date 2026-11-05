# Job Scout

Job Scout collects the Job Postings you find, evaluates each against your Career Profile and Deal Breakers, and helps you apply. See [GLOSSARY.md](GLOSSARY.md) for its language and [docs/adr/](docs/adr/) for its decisions.

The webapp lives in [webapp/](webapp/): a FastAPI backend with a Procrastinate background worker in [webapp/backend/](webapp/backend/), and a React single-page app in [webapp/frontend/](webapp/frontend/).

## Run the app

You need Docker with Compose.

```sh
docker compose up --build
```

Then open <http://localhost:5173>. Compose starts Postgres, applies the migrations, and runs the API (<http://localhost:8000/docs>), the background worker and the frontend. There is no login while the app runs locally.

All configuration comes from environment variables, each with a default in [compose.yaml](compose.yaml): `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `API_PORT` and `FRONTEND_PORT`. Set them in your shell or in a `.env` file next to `compose.yaml`. The backend itself reads `DATABASE_URL`.

The background worker makes every LLM call, through the Anthropic API:

- `ANTHROPIC_API_KEY`: your API key. Without it the app still runs, but every LLM step fails with a reason saying the key is not set.
- `EXTRACTION_MODEL`: the model that reads a pasted Job Posting (default `claude-opus-5-5`).
- `EXTRACTION_EFFORT`: how hard that model thinks, one of `low`, `medium`, `high`, `xhigh` or `max`. Unset, the API's default applies; not every model accepts every level.
- `EVALUATION_MODEL` and `EVALUATION_EFFORT`: the same for the model that evaluates a saved Job Posting against the Career Profile, Preferences and Deal Breakers.
- `COVER_LETTER_MODEL` and `COVER_LETTER_EFFORT`: the same for the model that writes a Cover Letter draft from the posting, the Career Profile, the Evaluation's flags and the Writing Guide.
- `LLM_RETRY_WAIT_SECONDS`: how long a failed LLM call waits before the queue tries it again (default 30). After three failed attempts the reason is shown and the user retries by hand. An Evaluation whose answer fails a check (a quote not in the posting, a missing verdict, a score out of range, too many flags) counts as failed too.

Prompts live in `webapp/backend/src/job_scout/prompts/`, one file per step, each starting with a `version:` header that every LLM-produced record stores. Bump the version whenever you change a prompt's text.

## Test

The backend tests drive the HTTP API against a real Postgres, which they start in a throwaway container, so Docker must be running. Queued tasks run to completion inside the test. You need [uv](https://docs.astral.sh/uv/).

```sh
cd webapp/backend
uv run pytest          # tests
uv run mypy src tests  # type checks
uv run ruff check .    # lint
uv run lint-imports    # the backend's package order (also run by the tests)
```

The browser tests drive the React app in headless Chromium, against the API and the fake LLM: a smoke test that pastes, confirms and saves a posting, and tests of the Markdown editor on the Document pages. They need the frontend's packages (`npm ci` in `webapp/frontend`) and Chromium (`uv run playwright install chromium` in `webapp/backend`, once). Leave them out with `uv run pytest -m "not browser"`.

Type-check the frontend with `npm run typecheck` in `webapp/frontend`.

## Develop

- **API client**: the frontend's client in `webapp/frontend/src/api` is generated from the backend's OpenAPI schema. After changing the HTTP API, run `npm run generate-api` in `webapp/frontend` (it needs uv) and commit the result.
- **Migrations**: after changing the models, create a migration with `DATABASE_URL=... uv run alembic revision --autogenerate -m "..."` in `webapp/backend` against a migrated database, review it, and apply it with `uv run python -m job_scout.migrations`.

## Backend layout

The backend in `webapp/backend/src/job_scout/` has one package per domain concept ([ADR-0004](docs/adr/0004-backend-code-is-one-package-per-domain-concept.md)). A change to one concept should stay inside its folder. Every package has the same four files:

- `routes.py`: the FastAPI routes. They parse the request, call the package and map its errors to HTTP. They hold no rules.
- `schemas.py`: the Pydantic request and response models.
- `models.py`: the package's SQLAlchemy tables.
- `domain.py`: the package's rules and queries.

Some packages have more modules: `prompt.py` (building an LLM prompt), `tasks.py` (a background task the worker runs) and `extraction.py` (what the LLM returns).

A package imports only from the packages below it. From the top:

1. `posting_view`: how a Job Posting appears in lists and on its page
2. `notes`, `cover_letters`
3. `clippings`, `applications`
4. `triage`, `evaluations`
5. `posting_text`: a Job Posting as the LLM reads it, and the check that a quote is in it; `llm_runs`: the lifecycle of every background job that calls the LLM (queueing, status, retries, failures, and stuck runs), which each feature plugs into with a job in its `tasks.py`
6. `user_inputs`, `job_postings`

Packages on the same line don't import each other. Above them all is the wiring that starts the app: `app` (the API), `worker`, `runtime`, `tables`, and the LLM adapters in `llm/`. Below them all is what every package may use: `db`, `config`, `prompts`, `llm.interface`, the task `queue`, `owners`, and what routes share (`routing`, `fields`).

- **Coordinating several concepts:** code that does this goes in the highest package involved. It never goes in a lower package reaching up.
- **Shared code:** goes in a module named for a concept, never `utils` or `common`.
- **Exceptions:** a few are allowed, each listed with its reason in the `[tool.importlinter]` contract in `webapp/backend/pyproject.toml`.
  - Any route may return a Job Posting as `posting_view` shows it.
  - Two upward calls remain until #42 and #43 remove them.
- **Foreign keys:** they name tables by string, so they need no imports. A `relationship()` to a higher package quotes the class name and imports it only under `TYPE_CHECKING`.

`uv run lint-imports` checks the order, and `tests/test_architecture.py` runs that same check.

- **Adding a package:** give it a line in the contract (the check fails until you do), and add its `models.py` to `job_scout/tables.py`. `tables.py` registers every table for SQLAlchemy and Alembic. A package missing from it is invisible to autogenerated migrations.
