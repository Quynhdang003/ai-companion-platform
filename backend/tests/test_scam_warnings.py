import re

import pytest

from app.models import RiskLevel, ScamType
from app.services.scam.warnings import ADVICE, warning_message


def test_every_type_has_advice() -> None:
    assert set(ADVICE) == set(ScamType)


@pytest.mark.parametrize("level", [RiskLevel.MEDIUM, RiskLevel.HIGH])
@pytest.mark.parametrize("scam_type", list(ScamType))
def test_warnings_end_with_the_advice_for_the_type(level: RiskLevel, scam_type: ScamType) -> None:
    assert warning_message(level, scam_type).endswith(ADVICE[scam_type])


@pytest.mark.parametrize("level", list(RiskLevel))
@pytest.mark.parametrize("scam_type", [None, *ScamType])
def test_messages_are_speakable(level: RiskLevel, scam_type: ScamType | None) -> None:
    message = warning_message(level, scam_type)

    assert message.startswith("Dạ, ")
    # No symbols, digits or list marks for TTS to stumble on.
    assert not re.search(r"[0-9#*/\\_\[\]{}<>@%-]", message)


def test_low_and_none_differ_and_name_no_type() -> None:
    low = warning_message(RiskLevel.LOW, None)
    none = warning_message(RiskLevel.NONE, None)

    assert low != none
    assert all(advice not in low + none for advice in ADVICE.values())
