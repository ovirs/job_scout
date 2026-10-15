from pydantic_settings import BaseSettings
from sqlalchemy import make_url


class Settings(BaseSettings):
    """All configuration, read from environment variables."""

    # A libpq URL, e.g. postgresql://job_scout:secret@localhost:5432/job_scout
    database_url: str

    @property
    def sqlalchemy_url(self) -> str:
        url = make_url(self.database_url).set(drivername="postgresql+psycopg")
        return url.render_as_string(hide_password=False)
