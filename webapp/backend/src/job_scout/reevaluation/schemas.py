from pydantic import BaseModel


class RerunQueuedRead(BaseModel):
    queued: int  # the Evaluations queued, one per posting
