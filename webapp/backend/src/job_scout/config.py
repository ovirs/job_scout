from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url


class Settings(BaseSettings):
    """All configuration, read from environment variables: only infrastructure. The
    Provider keys and the model for each LLM step are the user's own Settings, stored per
    owner by the `settings` package."""

    # Compose passes unset optional variables as empty strings; read those as not set
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # A libpq URL, e.g. postgresql://job_scout:secret@localhost:5432/job_scout
    database_url: str

    # How long a failed LLM call waits on the queue before its next attempt
    llm_retry_wait_seconds: int = 30

    @property
    def sqlalchemy_url(self) -> str:
        url = make_url(self.database_url).set(drivername="postgresql+psycopg")
        return url.render_as_string(hide_password=False)
