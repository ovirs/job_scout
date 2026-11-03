"""What the LLM reads from a Clipping's pasted text."""

from job_scout.job_postings.extraction import ExtractedFields


class ManualEntryExtraction(ExtractedFields):
    """What the LLM reads from a Clipping's pasted text: the facts plus the envelope.

    The description is not retyped: the LLM names its first and last line,
    verbatim, and code cuts it from the pasted text.
    """

    title: str | None
    company: str | None
    location_text: str | None
    description_first_line: str | None
    description_last_line: str | None

    def extracted_fields(self) -> ExtractedFields:
        return ExtractedFields.model_validate(
            self.model_dump(include=set(ExtractedFields.model_fields))
        )
