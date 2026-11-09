"""Load the sample knowledge-base documents (`backend/data/kb/*.md`) into the database.

Run from backend/: `uv run python -m scripts.seed_kb` (needs GEMINI_API_KEY: one embedding
request per new or changed document). Running it again is safe: unchanged documents are
skipped, changed ones are replaced in place. Each file starts with `# Title`; the rest is
the content.
"""

import asyncio
import sys
from pathlib import Path

from app.core.db import SessionLocal
from app.llm.client import get_llm_client
from app.services.rag.ingest import sync_document

KB_DIR = Path(__file__).resolve().parents[1] / "data" / "kb"


def parse(path: Path) -> tuple[str, str]:
    """(title, content) from a `# Title` markdown file."""
    first, _, rest = path.read_text(encoding="utf-8").strip().partition("\n")
    if not first.startswith("# ") or not rest.strip():
        raise ValueError(f"{path.name}: expected '# Title' followed by the content")
    return first[2:].strip(), rest.strip()


async def main() -> None:
    llm = get_llm_client()
    async with SessionLocal() as db:
        for path in sorted(KB_DIR.glob("*.md")):
            title, content = parse(path)
            result = await sync_document(
                db, llm, title=title, content=content, source=f"data/kb/{path.name}"
            )
            await db.commit()
            print(f"{result.value:<9} {title}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main())
