"""What the LLM writes a Cover Letter from, and the shape of its answer.

The prompt puts the unchanging part first so it can be cached: the Career
Profile and the Writing Guide, then the posting as untrusted third-party text,
the Evaluation's flags when there are any, the draft to revise when revising in
words, and the user's instruction for this one letter. Preferences and Deal
Breakers are never sent, so the user's private reasons cannot leak into a letter
a company reads.
"""

from dataclasses import dataclass

from pydantic import BaseModel

from job_scout.evaluation import PostingText


class CoverLetterResult(BaseModel):
    """The LLM's answer."""

    letter: str  # plain text, in the posting's language unless the instruction says otherwise
    # What the posting asks for that the Career Profile gives no support for
    unsupported_requirements: list[str]


@dataclass(frozen=True)
class Flags:
    """The points of an Evaluation's flags, as hints on what to stress and what to address."""

    green: list[str]
    red: list[str]


@dataclass(frozen=True)
class CoverLetterPrompt:
    """The two user blocks of a Cover Letter call, after the instructions."""

    user_inputs: str  # Career Profile and Writing Guide; cacheable
    # the Job Posting, the flags if any, the draft to revise if any and the instruction if any
    request: str

    @property
    def blocks(self) -> list[str]:
        """The blocks in the order they are sent."""
        return [self.user_inputs, self.request]


def prompt(
    *,
    career_profile: str,
    writing_guide: str | None,
    posting: PostingText,
    flags: Flags | None,
    draft: str | None,
    instruction: str | None,
) -> CoverLetterPrompt:
    """Lay out a Cover Letter's inputs; with no `flags`, the request says nothing of them,
    and with a `draft`, it asks for that text revised rather than a letter from scratch."""
    user_inputs = "\n\n".join(
        [
            _tagged("career_profile", career_profile),
            _tagged(
                "writing_guide",
                (writing_guide or "").strip() or "(The person has written no Writing Guide.)",
            ),
        ]
    )
    lines = [f"Title: {posting.title}", f"Company: {posting.company}"]
    if posting.location_text:
        lines.append(f"Location: {posting.location_text}")
    lines += ["Description:", posting.description]
    request = [_tagged("job_posting", "\n".join(lines))]
    if flags is not None:
        request.append(
            _tagged(
                "evaluation_flags",
                "\n".join(
                    ["Green flags (strengths to stress):"]
                    + _bullets(flags.green)
                    + ["Red flags (gaps or concerns to address or leave aside):"]
                    + _bullets(flags.red)
                ),
            )
        )
    if draft is not None:
        request.append(_tagged("draft_to_revise", draft))
    if instruction:
        request.append(_tagged("instructions_for_this_letter", instruction))
    return CoverLetterPrompt(user_inputs=user_inputs, request="\n\n".join(request))


def _bullets(points: list[str]) -> list[str]:
    return [f"- {point}" for point in points] or ["(none)"]


def _tagged(tag: str, text: str) -> str:
    return f"<{tag}>\n{text.strip()}\n</{tag}>"
