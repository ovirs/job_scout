from datetime import datetime

from pydantic import BaseModel

from job_scout.triage.models import Triage, TriageOrigin, TriageValue


class TriageSet(BaseModel):
    value: TriageValue


class TriageRead(BaseModel):
    value: TriageValue
    origin: TriageOrigin  # set by the user, or copied by the app
    created_at: datetime  # when the posting was first triaged
    changed_at: datetime  # when the value last changed

    @classmethod
    def of(cls, triage: Triage) -> "TriageRead":
        return cls(
            value=triage.value,
            origin=triage.origin,
            created_at=triage.created_at,
            changed_at=triage.changed_at,
        )
