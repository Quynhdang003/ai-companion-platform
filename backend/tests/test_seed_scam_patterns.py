from collections import Counter
from pathlib import Path

import pytest

from app.models import ScamType
from app.services.scam.patterns import MAX_PATTERN_CHARS, MAX_TITLE_CHARS
from scripts.seed_scam_patterns import PATTERNS_DIR, load_all, parse

KNOWN_TYPES = [t for t in ScamType if t is not ScamType.OTHER]


def test_every_scam_type_has_a_sample_file() -> None:
    assert sorted(p.stem for p in PATTERNS_DIR.glob("*.md")) == sorted(t.value for t in ScamType)


def test_every_known_type_has_at_least_three_patterns() -> None:
    counts = Counter(p.scam_type for p in load_all())

    assert all(counts[t] >= 3 for t in KNOWN_TYPES), counts


def test_sample_patterns_are_valid() -> None:
    patterns = load_all()

    assert len({p.title for p in patterns}) == len(patterns)
    for pattern in patterns:
        assert 0 < len(pattern.title) <= MAX_TITLE_CHARS
        assert 0 < len(pattern.content) <= MAX_PATTERN_CHARS, pattern.title
        assert "##" not in pattern.content
        assert pattern.source == f"data/scam_patterns/{pattern.scam_type.value}.md"


def test_file_is_parsed_into_its_sections(tmp_path: Path) -> None:
    path = tmp_path / "investment.md"
    path.write_text(
        "# Đầu tư\n## Tiền ảo\nHứa lãi cao.\n\nĐòi nạp thêm.\n\n## Đất nền\nGóp vốn.\n",
        encoding="utf-8",
    )

    patterns = parse(path)

    assert [(p.scam_type, p.title, p.content) for p in patterns] == [
        (ScamType.INVESTMENT, "Tiền ảo", "Hứa lãi cao.\n\nĐòi nạp thêm."),
        (ScamType.INVESTMENT, "Đất nền", "Góp vốn."),
    ]


@pytest.mark.parametrize(
    ("name", "body", "error"),
    [
        ("lottery.md", "# X\n\n## A\nB.", "not a scam type"),
        ("other.md", "Không có tiêu đề.\n## A\nB.", "heading"),
        ("other.md", "# X\nĐoạn mở đầu.\n\n## A\nB.", "only '## Title' sections"),
        ("other.md", "# X\n", "only '## Title' sections"),
        ("other.md", "# X\n\n## A\n\n## B\nC.", "'A' has no content"),
    ],
)
def test_malformed_file_is_rejected(tmp_path: Path, name: str, body: str, error: str) -> None:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        parse(path)
