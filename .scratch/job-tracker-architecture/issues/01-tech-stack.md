# What tech stack should we use for the web application?

Type: grilling
Status: resolved (2026-10-09)

## Question

We need to decide the core framework, backend (if separate), and database for the Job Tracker Web Application. This foundation will dictate how we build the ingestion pipelines and integrate with LLMs.

Options to consider:
- Next.js (React) + TypeScript (Full-stack)
- Python backend (Django/FastAPI for ETL/LLM) + React frontend
- Vue/Nuxt + TypeScript
- Go backend + React frontend

What is the preferred stack considering the user's ETL background and the heavy LLM/pipeline requirements?

## Answer

Two separate subsystems in one repository, both Python on the server side, joined only by the webapp's HTTP API.

- **Webapp**: FastAPI backend (Pydantic, SQLAlchemy 2, Alembic) and a React + TypeScript single-page frontend (Vite, TanStack Query, API client generated from the OpenAPI schema). No Next.js: the app sits behind a login and needs no server rendering.
- **ETL**: Airflow, with `httpx` and Pydantic and one adapter per ATS. Airflow is chosen partly as a learning goal. Pipelines poll the companies on the Watchlist; there is no cross-market search source, so keyword search is built over locally ingested Job Postings.
- **Boundary**: the ETL reads the Watchlist and bulk-upserts Job Postings through the webapp's API and never touches the application database. The webapp is the only writer. The upsert is idempotent; the ETL uses a service credential. See [ADR 0001](../../../docs/adr/0001-etl-and-webapp-as-separate-subsystems-joined-by-the-api.md).
- **Database**: PostgreSQL, one instance, with one database for the webapp and one for Airflow's metadata.
- **LLM**: all calls are made by the webapp, in a background worker fed by a Postgres-backed queue (Procrastinate), never in a request handler. Anthropic Python SDK behind a thin internal interface. Model choice is left to the LLM evaluation ticket.
- **Watchlist**: maintained through the webapp UI.
- **Running it**: local first with Docker Compose, all configuration from environment variables so a move to a home server or cloud is a configuration change. No login while local.
- **Multi-user hedge**: user-owned tables carry an owner column from the start, with a single user. Nothing else is built for multi-tenancy.
- **Tooling and layout**: `uv` for Python; `webapp/backend`, `webapp/frontend` and `etl` directories with a Compose file at the root.

Rejected: a single TypeScript full-stack app (the user wants Python and separate subsystems); a shared database with per-subsystem schemas (weaker boundary, two writers); LLM work in Airflow or in a third subsystem (splits prompt logic or adds moving parts); LinkedIn scraping, direct or through paid services (against LinkedIn's terms).
