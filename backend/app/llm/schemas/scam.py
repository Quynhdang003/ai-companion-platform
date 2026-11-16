from pydantic import BaseModel, Field, model_validator

from app.models import RiskLevel, ScamType, Signal


class ScamClassification(BaseModel):
    """Layer 2 of the Scam Risk Engine (`app/services/scam/classifier.py`).

    `signals` are codes only, so nothing the caller said can reach storage through them.
    `reason` is for evaluation (`scripts.eval_scam`): never stored or logged.
    """

    risk_level: RiskLevel
    scam_type: ScamType | None = Field(
        default=None, description="Required for medium and high; null for low and none."
    )
    signals: list[Signal] = Field(default_factory=list, max_length=10)
    reason: str = Field(
        default="",
        max_length=300,
        description="One short Vietnamese sentence: why this level. No names or numbers.",
    )

    @model_validator(mode="after")
    def _type_matches_level(self) -> "ScamClassification":
        if self.risk_level.rank >= RiskLevel.MEDIUM.rank:
            if self.scam_type is None:
                raise ValueError("scam_type is required for medium and high")
        else:
            # Below medium there is no scam to name.
            self.scam_type = None
        return self
