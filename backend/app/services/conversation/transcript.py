"""Parse Dograh's transcript file into turns.

Dograh 1.50.0 writes one line per final message, `[<ISO time>] user: <text>` or
`[<ISO time>] assistant: <text>` (the timestamp prefix can be missing); a message with
line breaks continues on the following lines without a prefix.
"""

import re
from typing import Literal, TypedDict

_LINE = re.compile(r"^(?:\[[^\]]*\] )?(?P<role>user|assistant): ?(?P<text>.*)$")
_ROLES: dict[str, Literal["elder", "assistant"]] = {"user": "elder", "assistant": "assistant"}


class Turn(TypedDict):
    role: Literal["elder", "assistant"]
    text: str


class TranscriptFormatError(Exception):
    """The file doesn't look like a Dograh transcript."""


def parse_dograh_transcript(raw: str) -> list[Turn]:
    turns: list[Turn] = []
    for line in raw.splitlines():
        match = _LINE.match(line)
        if match:
            turns.append({"role": _ROLES[match["role"]], "text": match["text"].strip()})
        elif turns:
            turns[-1]["text"] = f"{turns[-1]['text']}\n{line.strip()}".strip()
        elif line.strip():
            raise TranscriptFormatError("text before the first message")
    return [turn for turn in turns if turn["text"]]
