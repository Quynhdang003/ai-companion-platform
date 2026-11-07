"""Split a document into overlapping chunks for search.

Packs whole sentences (and headings or list items, one per line) into chunks of at most
`max_chars`; each new chunk repeats the last sentences of the previous one, up to `overlap`
characters, so a fact cut at a boundary is still found whole. Only a sentence longer than
`max_chars` is cut, between words.
"""

import re
from dataclasses import dataclass

MAX_CHARS = 800
OVERLAP = 100

_PARAGRAPHS = re.compile(r"\n\s*\n")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class _Unit:
    text: str
    # Starts a new paragraph or line (joined with "\n"), else continues one (joined with " ").
    new_line: bool


def chunk_text(text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")
    chunks: list[str] = []
    current: list[_Unit] = []
    for unit in _units(text, max_chars):
        if current and _length(current + [unit]) > max_chars:
            chunks.append(_join(current))
            current = _tail(current, overlap)
            while current and _length(current + [unit]) > max_chars:
                current = current[1:]
        current.append(unit)
    if current:
        chunks.append(_join(current))
    return chunks


def _units(text: str, max_chars: int) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in _PARAGRAPHS.split(text.replace("\r\n", "\n").strip()):
        for line in paragraph.split("\n"):
            line = " ".join(line.split())
            if not line:
                continue
            for i, sentence in enumerate(_SENTENCE_END.split(line)):
                for j, piece in enumerate(_cut(sentence, max_chars)):
                    units.append(_Unit(piece, new_line=i == 0 and j == 0))
    return units


def _cut(sentence: str, max_chars: int) -> list[str]:
    """A sentence longer than max_chars, cut between words (or mid-word if it must)."""
    pieces: list[str] = []
    piece = ""
    for word in sentence.split(" "):
        while len(word) > max_chars:
            if piece:
                pieces.append(piece)
                piece = ""
            pieces.append(word[:max_chars])
            word = word[max_chars:]
        candidate = f"{piece} {word}" if piece else word
        if len(candidate) > max_chars:
            pieces.append(piece)
            piece = word
        else:
            piece = candidate
    if piece:
        pieces.append(piece)
    return pieces


def _tail(units: list[_Unit], overlap: int) -> list[_Unit]:
    """The last units whose text fits in `overlap` characters."""
    tail: list[_Unit] = []
    for unit in reversed(units):
        if _length([unit, *tail]) > overlap:
            break
        tail.insert(0, unit)
    return tail


def _join(units: list[_Unit]) -> str:
    text = units[0].text
    for unit in units[1:]:
        text += ("\n" if unit.new_line else " ") + unit.text
    return text


def _length(units: list[_Unit]) -> int:
    return len(_join(units)) if units else 0
