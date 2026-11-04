"""A Job Posting as the LLM reads it: the block every prompt sends, and the check that a
quote the LLM took from it is really there."""

import pytest

from job_scout.posting_text import EvidenceMatch, PostingField, PostingText

DESCRIPTION = """About the job
We are building the data platform behind Acme's payments.
• You will design batch and streaming pipelines in Python.
- The team works “remote-first” from anywhere in Romania.
Spark experience is a nice to have."""

POSTING = PostingText(
    title="Senior Data Engineer",
    company="Acme",
    location_text="Bucharest, Romania",
    description=DESCRIPTION,
)


def test_the_posting_is_rendered_as_one_tagged_block_with_each_field_labelled() -> None:
    assert POSTING.render() == (
        "<job_posting>\n"
        "Title: Senior Data Engineer\n"
        "Company: Acme\n"
        "Location: Bucharest, Romania\n"
        "Description:\n"
        f"{DESCRIPTION}\n"
        "</job_posting>"
    )


def test_a_posting_with_no_location_is_rendered_without_the_location_line() -> None:
    posting = PostingText(
        title="Data Engineer", company="Acme", location_text=None, description="Pipelines."
    )

    assert posting.render() == (
        "<job_posting>\n"
        "Title: Data Engineer\n"
        "Company: Acme\n"
        "Description:\n"
        "Pipelines.\n"
        "</job_posting>"
    )


def matched(field: PostingField, text: str, starts_with: str, ends_with: str) -> EvidenceMatch:
    """Where a passage of `text` runs, from the first `starts_with` to the `ends_with` after it."""
    start = text.index(starts_with)
    return EvidenceMatch(
        field=field, start=start, end=text.index(ends_with, start) + len(ends_with)
    )


@pytest.mark.parametrize(
    ("quote", "starts_with", "ends_with"),
    [
        ("We are building the data platform", "We are building", "data platform"),
        # Case and whitespace, including a line break in the quote
        (
            "you will design   BATCH and\nstreaming pipelines in python.",
            "You will design",
            "in Python.",
        ),
        # Straight quotes for the posting's curly ones
        ('works "remote-first" from', "works “remote-first”", "from"),
        # Across two bulleted lines, the bullets dropped
        ("pipelines in Python. The team works", "pipelines in Python.", "The team works"),
        # The quote keeps a bullet the posting has
        ("- The team works", "The team works", "The team works"),
        ("• You will design", "You will design", "You will design"),
    ],
)
def test_a_quote_matches_the_description_ignoring_whitespace_case_quote_styles_and_bullets(
    quote: str, starts_with: str, ends_with: str
) -> None:
    assert POSTING.find(quote) == matched("description", DESCRIPTION, starts_with, ends_with)


def test_a_quote_from_the_title_matches_there() -> None:
    assert POSTING.find("senior data") == EvidenceMatch(field="title", start=0, end=11)


def test_a_quote_in_both_the_description_and_another_field_matches_the_description() -> None:
    assert POSTING.find("Acme") == matched("description", DESCRIPTION, "Acme", "Acme")


@pytest.mark.parametrize(
    ("quote", "field", "value"),
    [
        ("Title: Senior Data Engineer", "title", "Senior Data Engineer"),
        ("Company: Acme", "company", "Acme"),
        ("location:  bucharest, romania", "location_text", "Bucharest, Romania"),
        ("Description: About the job", "description", "About the job"),
    ],
)
def test_a_quote_with_the_label_its_field_is_rendered_with_matches_the_value_after_it(
    quote: str, field: PostingField, value: str
) -> None:
    # The match highlights the value, not the label the posting does not contain
    assert POSTING.find(quote) == EvidenceMatch(field=field, start=0, end=len(value))


@pytest.mark.parametrize(
    "quote",
    [
        "unpaid weekend on-call",
        "",
        "  • ",
        # A label only matches with its own field's text after it
        "Company: Senior Data",
        "Title:",
    ],
)
def test_a_quote_of_words_the_posting_does_not_contain_matches_nothing(quote: str) -> None:
    assert POSTING.find(quote) is None
