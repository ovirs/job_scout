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

## Test

The backend tests drive the HTTP API against a real Postgres, which they start in a throwaway container, so Docker must be running. Queued tasks run to completion inside the test. You need [uv](https://docs.astral.sh/uv/).

```sh
cd webapp/backend
uv run pytest          # tests
uv run mypy src tests  # type checks
uv run ruff check .    # lint
```

Type-check the frontend with `npm run typecheck` in `webapp/frontend`.

## Develop

- **API client**: the frontend's client in `webapp/frontend/src/api` is generated from the backend's OpenAPI schema. After changing the HTTP API, run `npm run generate-api` in `webapp/frontend` (it needs uv) and commit the result.
- **Migrations**: after changing the models, create a migration with `DATABASE_URL=... uv run alembic revision --autogenerate -m "..."` in `webapp/backend` against a migrated database, review it, and apply it with `uv run python -m job_scout.migrations`.
