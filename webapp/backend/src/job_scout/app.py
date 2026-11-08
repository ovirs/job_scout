"""The webapp's HTTP API. Serve with `uvicorn job_scout.app:create_app --factory`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from job_scout import tables  # noqa: F401  # registers every table before the first query
from job_scout.applications.routes import router as applications
from job_scout.clippings.routes import router as clippings
from job_scout.config import Settings
from job_scout.cover_letters.routes import router as cover_letters
from job_scout.evaluations.routes import router as evaluations
from job_scout.job_postings.routes import router as job_postings
from job_scout.llm.interface import ModelLister
from job_scout.llm.providers import ProviderModelLister
from job_scout.notes.routes import router as notes
from job_scout.posting_view.routes import router as posting_view
from job_scout.runtime import open_runtime
from job_scout.settings.routes import router as settings_routes
from job_scout.user_inputs.routes import router as user_inputs

# Each package's routes, in the order the OpenAPI schema lists them
ROUTERS = [
    posting_view,
    applications,  # the Triage route included, first
    notes,
    job_postings,
    evaluations,
    cover_letters,
    clippings,
    user_inputs,
    settings_routes,
]


def create_app(
    settings: Settings | None = None, *, model_lister: ModelLister | None = None
) -> FastAPI:
    """The API; a key is checked by listing its Provider's models, through the Providers'
    APIs unless another `model_lister` is given."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        nonlocal settings
        settings = settings or Settings()  # read from the environment
        async with open_runtime(settings) as runtime:
            app.state.sessions = runtime.sessions
            app.state.task_queue = runtime.task_queue
            app.state.model_lister = model_lister or ProviderModelLister()
            yield

    app = FastAPI(
        title="Job Scout",
        lifespan=lifespan,
        # Operation ids name the generated client's functions
        generate_unique_id_function=lambda route: route.name,
    )
    for router in ROUTERS:
        app.include_router(router)
    return app
