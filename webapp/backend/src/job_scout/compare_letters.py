"""Compare Cover Letters: a backend command the user starts to judge a new prompt version
or model by eye. Run from `webapp/backend`:

    uv run python -m job_scout.compare_letters --application 3 --application 7 \\
        --prompt-file new-cover-letter.md --model claude-sonnet-5-5

For each chosen Application with a letter sent, it writes the letter again under the prompt
file (a prompt in the format of `prompts/cover-letter.md`, with its `version:` header) or
the model, and prints it beside the letter actually sent. It saves nothing: no draft is
made and the Cover Letters stay as they are.
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from job_scout import db, tables  # noqa: F401  # tables: registers every table
from job_scout.config import Settings
from job_scout.cover_letters import domain as cover_letters
from job_scout.llm.anthropic_adapter import AnthropicLlm
from job_scout.llm.interface import Failure, Llm
from job_scout.owners import current_owner
from job_scout.prompts import Prompt, parse


async def run(
    settings: Settings,
    argv: Sequence[str],
    *,
    llm: Llm | None = None,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
) -> int:
    """Run the command with its arguments; returns the exit status. LLM calls go to the
    Anthropic API unless another `llm` is given."""
    parser = argparse.ArgumentParser(prog="job_scout.compare_letters", description=__doc__)
    parser.add_argument(
        "--application",
        type=int,
        action="append",
        required=True,
        dest="applications",
        metavar="ID",
        help="an Application that has had a letter sent; repeat for each",
    )
    parser.add_argument("--prompt-file", type=Path, help="the prompt version to write under")
    parser.add_argument("--model", help="the model to write with")
    args = parser.parse_args(argv)
    if args.prompt_file is None and args.model is None:
        parser.error("give --prompt-file, --model or both: there is nothing to compare otherwise")
    instructions: Prompt | None = None
    if args.prompt_file is not None:
        try:
            instructions = parse(
                args.prompt_file.read_text(encoding="utf-8"), str(args.prompt_file)
            )
        except (OSError, ValueError) as error:
            print(f"Cannot read the prompt: {error}", file=err)
            return 1

    engine = db.create_engine(settings)
    try:
        async with db.create_sessionmaker(engine)() as session:
            try:
                comparisons = await cover_letters.compare(
                    session,
                    llm or AnthropicLlm(settings),
                    owner_id=current_owner(),
                    application_ids=args.applications,
                    instructions=instructions,
                    model=args.model,
                )
            except cover_letters.NoSuchApplication:
                print("No such Application: one is unknown or deleted", file=err)
                return 1
            except cover_letters.Refused as refusal:
                print(str(refusal), file=err)
                return 1
    finally:
        await engine.dispose()

    for comparison in comparisons:
        application = comparison.application
        posting = application.job_posting
        print(
            f"=== Application {application.id}: {posting.title} at {posting.company} ===", file=out
        )
        print("--- Sent ---", file=out)
        print(comparison.sent.text, file=out)
        print(
            f"--- Written again (model {comparison.model}, prompt {comparison.prompt_version}) ---",
            file=out,
        )
        result = comparison.regenerated
        print(
            f"The LLM call failed: {result.reason}" if isinstance(result, Failure) else result,
            file=out,
        )
        print(file=out)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run(Settings(), sys.argv[1:])))
