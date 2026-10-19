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
```

One browser smoke test pastes, confirms and saves a posting through the React app, in headless Chromium, against the API and the fake LLM. It needs the frontend's packages (`npm ci` in `webapp/frontend`) and Chromium (`uv run playwright install chromium` in `webapp/backend`, once). Leave it out with `uv run pytest -m "not browser"`.

Type-check the frontend with `npm run typecheck` in `webapp/frontend`.

## Develop

- **API client**: the frontend's client in `webapp/frontend/src/api` is generated from the backend's OpenAPI schema. After changing the HTTP API, run `npm run generate-api` in `webapp/frontend` (it needs uv) and commit the result.
- **Migrations**: after changing the models, create a migration with `DATABASE_URL=... uv run alembic revision --autogenerate -m "..."` in `webapp/backend` against a migrated database, review it, and apply it with `uv run python -m job_scout.migrations`.
