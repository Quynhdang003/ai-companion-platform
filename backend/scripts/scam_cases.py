"""The labelled scam test set (`backend/data/scam_eval/cases.jsonl`, see its README).

Used by the layer-1 tests and by the engine evaluation (`scripts.eval_scam`, SCAM-03).
"""

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import RiskLevel, ScamType

CASES_FILE = Path(__file__).resolve().parents[1] / "data" / "scam_eval" / "cases.jsonl"


class CaseTag(StrEnum):
    # Written like STT output: no diacritics, lower case.
    NO_DIACRITICS = "no_diacritics"
    # One short sentence.
    SHORT = "short"
    # Harmless, but shares words or a story with a scam.
    LOOK_ALIKE = "look_alike"


class ScamCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(pattern=r"^[a-z]+-\d{2}$")
    level: RiskLevel
    # The scam it is, for medium and high; null for harmless cases.
    scam_type: ScamType | None
    tags: tuple[CaseTag, ...] = ()
    # As the call agent would describe it to the check_scam tool.
    situation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def _type_matches_level(self) -> "ScamCase":
        if (self.scam_type is None) != (self.level.rank < RiskLevel.MEDIUM.rank):
            raise ValueError("scam_type is set exactly for medium and high cases")
        return self


def load_cases(path: Path = CASES_FILE) -> list[ScamCase]:
    cases = [
        ScamCase.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    ids = [case.id for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError(f"{path.name}: duplicate case ids")
    return cases
