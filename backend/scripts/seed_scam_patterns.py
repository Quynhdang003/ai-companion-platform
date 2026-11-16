"""Load the sample scam patterns (`backend/data/scam_patterns/<scam_type>.md`) into the database.

Run from backend/: `uv run python -m scripts.seed_scam_patterns` (needs GEMINI_API_KEY: one
embedding request for all new or changed patterns). Running it again is safe: unchanged
patterns are skipped, changed ones are replaced in place.

Each file is named after a `ScamType` value and holds that type's patterns: a `# Type`
heading, then one `## Pattern title` section per pattern, its content below.
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

from app.core.db import SessionLocal
from app.llm.client import get_llm_client
from app.models import ScamType
from app.services.scam.patterns import PatternIn, sync_patterns

PATTERNS_DIR = Path(__file__).resolve().parents[1] / "data" / "scam_patterns"


def parse(path: Path) -> list[PatternIn]:
    """The patterns in one `<scam_type>.md` file."""
    try:
        scam_type = ScamType(path.stem)
    except ValueError:
        raise ValueError(f"{path.name}: file name is not a scam type") from None
    first, _, rest = path.read_text(encoding="utf-8").strip().partition("\n")
    if not first.startswith("# "):
        raise ValueError(f"{path.name}: expected a '# Type' heading first")
    intro, *sections = f"\n{rest}".split("\n## ")
    if intro.strip() or not sections:
        raise ValueError(f"{path.name}: expected only '## Title' sections after the heading")

    patterns = []
    for section in sections:
        title, _, content = section.partition("\n")
        if not content.strip():
            raise ValueError(f"{path.name}: pattern '{title.strip()}' has no content")
        patterns.append(
            PatternIn(
                scam_type=scam_type,
                title=title.strip(),
                content=content.strip(),
                source=f"data/scam_patterns/{path.name}",
            )
        )
    return patterns


def load_all() -> list[PatternIn]:
    return [pattern for path in sorted(PATTERNS_DIR.glob("*.md")) for pattern in parse(path)]


async def main() -> None:
    patterns = load_all()
    async with SessionLocal() as db:
        results = await sync_patterns(db, get_llm_client(), patterns)
        await db.commit()
    for pattern, result in zip(patterns, results, strict=True):
        print(f"{result.value:<9} {pattern.scam_type.value:<22} {pattern.title}")
    print(", ".join(f"{count} {result.value}" for result, count in Counter(results).items()))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
