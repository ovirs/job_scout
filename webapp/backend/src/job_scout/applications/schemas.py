from datetime import datetime

from pydantic import BaseModel

from job_scout.applications import domain as applications
from job_scout.applications.models import Application, ApplicationState


class ApplicationBriefRead(BaseModel):
    """What a posting shows of its live Application."""

    id: int
    state: ApplicationState

    @classmethod
    def of(cls, application: Application) -> "ApplicationBriefRead":
        return cls(id=application.id, state=application.state)


class ApplicationStateSet(BaseModel):
    state: ApplicationState


class ApplicationStateChangeRead(BaseModel):
    state: ApplicationState
    changed_at: datetime


class PostingCopyRead(BaseModel):
    """The posting as it was when the Application first moved to Applied."""

    title: str
    company: str
    location_text: str | None
    description: str
    url: str | None
    copied_at: datetime


class ApplicationRead(BaseModel):
    id: int
    job_posting_id: int
    state: ApplicationState
    closed: bool  # Accepted, Rejected, Withdrawn or No response
    created_at: datetime
    state_changed_at: datetime  # when it moved to its current state
    history: list[ApplicationStateChangeRead]  # every move, the first first
    # The posting as it is now
    job_posting_title: str
    job_posting_company: str
    job_posting_closed_at: datetime | None
    posting_copy: PostingCopyRead | None  # null until the first move to Applied
    posting_changed_since_copy: bool | None  # the posting's text changed; null with no copy

    @classmethod
    def of(cls, application: Application) -> "ApplicationRead":
        return cls(
            id=application.id,
            job_posting_id=application.job_posting_id,
            state=application.state,
            closed=applications.is_closed(application),
            created_at=application.created_at,
            state_changed_at=applications.state_changed_at(application),
            history=[
                ApplicationStateChangeRead(state=change.state, changed_at=change.changed_at)
                for change in application.history
            ],
            job_posting_title=application.job_posting.title,
            job_posting_company=application.job_posting.company,
            job_posting_closed_at=application.job_posting.closed_at,
            posting_copy=_posting_copy(application),
            posting_changed_since_copy=applications.posting_changed_since_copy(application),
        )


def _posting_copy(application: Application) -> PostingCopyRead | None:
    if application.copied_at is None:
        return None
    assert application.copy_title is not None and application.copy_company is not None
    assert application.copy_description is not None
    return PostingCopyRead(
        title=application.copy_title,
        company=application.copy_company,
        location_text=application.copy_location_text,
        description=application.copy_description,
        url=application.copy_url,
        copied_at=application.copied_at,
    )
