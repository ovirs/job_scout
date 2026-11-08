"""The regeneration comparison command: write Cover Letters again for a handful of
Applications whose letter was sent, under another prompt or model, and print each beside
the letter sent. Nothing is saved. See `job_scout.cover_letters.comparison`.

    uv run python -m job_scout.compare_letters 12 15 --model claude-sonnet-5 \\
        --prompt candidate-cover-letter.md

With no `--model` or `--prompt`, the configured Cover Letter model and the app's own
Cover Letter prompt are used. A prompt file starts with a `version: ...` header, as the
app's prompts in `job_scout/prompts/` do.
"""

import argparse
import asyncio
import shutil
import sys
import textwrap
from itertools import zip_longest
from pathlib import Path

from job_scout import db, tables  # noqa: F401  # tables: registers every table
from job_scout.config import Settings
from job_scout.cover_letters.comparison import Comparison, NotComparable, comparisons
from job_scout.llm.anthropic_adapter import AnthropicLlm
from job_scout.llm.interface import Failure, Llm
from job_scout.owners import LOCAL_USER_ID
from job_scout.prompts import Prompt, parse

SEPARATOR = " │ "


async def run(argv: list[str], *, settings: Settings, llm: Llm | None = None) -> int:
    """Run the command with the arguments `argv`; returns its exit code: 0 when every
    letter was written again, 1 when any call failed, 2 when an Application chosen has no
    letter to compare with, in which case no letter is written. LLM calls go to the
    Anthropic API unless another `llm` is given."""
    args = _parser().parse_args(argv)
    instructions = None if args.prompt is None else _read_prompt(args.prompt)
    llm = llm or AnthropicLlm(settings)
    engine = db.create_engine(settings)
    try:
        async with db.create_sessionmaker(engine)() as session:
            try:
                chosen = await comparisons(
                    session, owner_id=LOCAL_USER_ID, application_ids=args.application_ids
                )
            except NotComparable as refused:
                for application_id, reason in refused.reasons.items():
                    print(f"Application {application_id}: {reason}", file=sys.stderr)
                return 2
            failed = False
            for comparison in chosen:
                outcome = await comparison.write_again(
                    llm, model=args.model, instructions=instructions
                )
                again = outcome.result
                if isinstance(again, Failure):
                    failed = True
                    written = f"(Not written: {again.reason})"
                else:
                    written = again.letter
                print(_header(comparison, outcome.model, outcome.prompt_version, args.width))
                print(_beside(comparison.sent.text, written, args.width))
                print()
    finally:
        await engine.dispose()
    return 1 if failed else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m job_scout.compare_letters",
        description="Write Cover Letters again for Applications whose letter was sent,"
        " and print each beside the letter sent. Nothing is saved.",
    )
    parser.add_argument(
        "application_ids", metavar="APPLICATION_ID", type=int, nargs="+", help="Applications"
    )
    parser.add_argument("--model", help="the model to write with; the configured one if unset")
    parser.add_argument(
        "--prompt",
        type=Path,
        help="a prompt file to write with, starting with a 'version: ...' header;"
        " the app's own Cover Letter prompt if unset",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=shutil.get_terminal_size().columns,
        help="the width to print in; the terminal's if unset",
    )
    return parser


def _read_prompt(path: Path) -> Prompt:
    return parse(path.read_text(encoding="utf-8"), str(path))


def _header(comparison: Comparison, model: str, prompt_version: str, width: int) -> str:
    application = comparison.application
    title = f"Application {application.id}: {application.copy_title} at {application.copy_company}"
    column = _column_width(width)
    left = f"Sent ({comparison.sent.created_at:%Y-%m-%d})"
    right = f"Written again: model {model}, prompt {prompt_version}"
    return "\n".join(
        [
            "=" * width,
            title,
            "=" * width,
            _row(left, right, column),
            _row("-" * column, "-" * column, column),
        ]
    )


def _beside(sent: str, written: str, width: int) -> str:
    """The two letters in two columns, wrapped to fit."""
    column = _column_width(width)
    lines = zip_longest(_wrap(sent, column), _wrap(written, column), fillvalue="")
    return "\n".join(_row(left, right, column) for left, right in lines)


def _column_width(width: int) -> int:
    return max(20, (width - len(SEPARATOR)) // 2)


def _wrap(text: str, column: int) -> list[str]:
    """The text wrapped to the column, keeping its line breaks and blank lines."""
    return [
        wrapped for line in text.splitlines() for wrapped in (textwrap.wrap(line, column) or [""])
    ]


def _row(left: str, right: str, column: int) -> str:
    return f"{left.ljust(column)}{SEPARATOR}{right}".rstrip()


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:], settings=Settings())))
