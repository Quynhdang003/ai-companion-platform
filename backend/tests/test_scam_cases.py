from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import RiskLevel, ScamType
from app.services.rag.search import fold
from scripts.scam_cases import CaseTag, load_cases

CASES = load_cases()


def test_every_scam_type_has_high_risk_cases() -> None:
    counts = Counter(case.scam_type for case in CASES if case.level is RiskLevel.HIGH)

    assert all(counts[t] >= 4 for t in ScamType), counts


def test_every_level_has_cases() -> None:
    counts = Counter(case.level for case in CASES)

    assert all(counts[level] >= 5 for level in RiskLevel), counts


def test_no_diacritics_cases_look_like_stt_output() -> None:
    stt = [case for case in CASES if CaseTag.NO_DIACRITICS in case.tags]

    assert len(stt) >= 6
    for case in stt:
        assert case.situation == fold(case.situation).lower(), case.id


@pytest.mark.parametrize(
    "line",
    [
        '{"id": "x-01", "level": "none", "scam_type": "other", "tags": [], "situation": "A"}',
        '{"id": "x-01", "level": "high", "scam_type": null, "tags": [], "situation": "A"}',
        '{"id": "x-01", "level": "high", "scam_type": "other", "tags": ["x"], "situation": "A"}',
        '{"id": "x-01", "level": "low", "scam_type": null, "situation": "A", "note": "?"}',
        '{"id": "X1", "level": "low", "scam_type": null, "situation": "A"}',
    ],
    ids=["type on harmless", "no type on high", "unknown tag", "extra field", "bad id"],
)
def test_malformed_case_is_rejected(tmp_path: Path, line: str) -> None:
    path = tmp_path / "cases.jsonl"
    path.write_text(line, encoding="utf-8")

    with pytest.raises(ValidationError):
        load_cases(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    line = '{"id": "x-01", "level": "none", "scam_type": null, "situation": "A"}'
    path = tmp_path / "cases.jsonl"
    path.write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_cases(path)
