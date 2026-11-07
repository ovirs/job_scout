from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import make_url

DEFAULT_MODEL = "claude-opus-5-5"

# How hard the model thinks, as the Anthropic API names the levels
type Effort = Literal["low", "medium", "high", "xhigh", "max"]


class Settings(BaseSettings):
    """All configuration, read from environment variables."""

    # Compose passes unset optional variables as empty strings; read those as not set
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # A libpq URL, e.g. postgresql://job_scout:secret@localhost:5432/job_scout
    database_url: str

    # The model for each LLM step
    extraction_model: str = DEFAULT_MODEL
    evaluation_model: str = DEFAULT_MODEL
    cover_letter_model: str = DEFAULT_MODEL

    # How hard the model thinks about each step; unset leaves it to the API's default
    extraction_effort: Effort | None = None
    evaluation_effort: Effort | None = None
    cover_letter_effort: Effort | None = None

    # How long a failed LLM call waits on the queue before its next attempt
    llm_retry_wait_seconds: int = 30

    @property
    def sqlalchemy_url(self) -> str:
        url = make_url(self.database_url).set(drivername="postgresql+psycopg")
        return url.render_as_string(hide_password=False)
