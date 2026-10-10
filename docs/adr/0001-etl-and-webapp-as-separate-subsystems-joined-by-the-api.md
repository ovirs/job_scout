# ETL and webapp are separate subsystems joined only by the webapp's API

The ETL (Airflow) and the webapp (FastAPI + React) are separate subsystems, and the ETL reaches application data only through the webapp's HTTP API: it reads the Watchlist and bulk-upserts Job Postings there, and never connects to the application database. We chose this over a shared Postgres with per-subsystem schemas because we wanted the webapp to be the single writer and the boundary between the two to be an explicit contract, accepting the cost of ETL-only endpoints and bulk loads over HTTP.

Airflow is heavier than polling a Watchlist of ATS boards needs; it was chosen deliberately because learning Airflow is a goal of the project, not because the workload demands an orchestrator.

## Consequences

- The Job Posting upsert endpoint must be idempotent, keyed on the ATS, the company and the ATS's own posting id, so re-running a DAG never duplicates.
- The ETL authenticates to the API with a service credential, separate from user login.
- The ETL owns no data store beyond Airflow's metadata database; anything worth keeping (including raw ATS payloads) is sent to the webapp.
- All LLM calls live in the webapp, in a background worker; Airflow only ingests.
