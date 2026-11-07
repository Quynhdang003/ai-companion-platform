from pathlib import Path

import pytest

from app.services.rag.chunking import MAX_CHARS, chunk_text
from scripts.seed_kb import KB_DIR, parse

SAMPLES = sorted(KB_DIR.glob("*.md"))


def test_sample_documents_exist() -> None:
    assert len(SAMPLES) >= 3


@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_sample_document_parses_and_chunks(path: Path) -> None:
    title, content = parse(path)

    assert title and not title.startswith("#")
    chunks = chunk_text(content)
    assert chunks and all(len(chunk) <= MAX_CHARS for chunk in chunks)


def test_file_without_title_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    path.write_text("Không có tiêu đề.\nNội dung.", encoding="utf-8")

    with pytest.raises(ValueError, match="x.md"):
        parse(path)
