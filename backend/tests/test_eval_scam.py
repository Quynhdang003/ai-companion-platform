from pathlib import Path

from app.models import RiskLevel, ScamType
from scripts.eval_scam import (
    CaseResult,
    append_cache,
    cache_key,
    format_report,
    load_cache,
    rules_result,
    summarize,
)
from scripts.scam_cases import ScamCase, load_cases


def case(case_id: str, level: str, scam_type: str | None, situation: str = "A") -> ScamCase:
    return ScamCase.model_validate(
        {"id": case_id, "level": level, "scam_type": scam_type, "situation": situation}
    )


def result(c: ScamCase, level: str, scam_type: str | None, by: str = "llm", latency: float = 1.0):
    return CaseResult(
        case_id=c.id,
        key=cache_key(c),
        level=RiskLevel(level),
        scam_type=ScamType(scam_type) if scam_type else None,
        assessed_by=by,
        latency_seconds=latency,
    )


BANK_1 = case("bank-01", "high", "bank_impersonation", "Họ xin mã OTP.")
BANK_2 = case("bank-02", "high", "bank_impersonation", "Họ xin mật khẩu.")
POLICE = case("police-01", "high", "police_impersonation", "Công an gọi.")
MEDIUM = case("medium-01", "medium", "investment", "Mời đầu tư.")
LOOK_ALIKE = case("lookalike-01", "low", None, "Cháu xin học phí.")
BENIGN = case("benign-01", "none", None, "Trời đẹp.")


def test_summary_counts_recall_and_false_alarms() -> None:
    cases = [BANK_1, BANK_2, POLICE, MEDIUM, LOOK_ALIKE, BENIGN]
    results = {
        r.case_id: r
        for r in [
            result(BANK_1, "high", "bank_impersonation", by="rules", latency=0),
            result(BANK_2, "medium", "other", latency=2.0),  # warned, wrong type
            result(MEDIUM, "high", "investment", latency=5.0),  # false high
            result(LOOK_ALIKE, "medium", "relative_impersonation", latency=1.0),
            result(BENIGN, "none", None, latency=0.5),
        ]
    }

    summary = summarize(cases, results)

    assert summary.evaluated == 5
    assert summary.pending == ["police-01"]
    bank = summary.by_type[ScamType.BANK_IMPERSONATION]
    assert (bank.cases, bank.high, bank.warned, bank.right_type) == (2, 1, 2, 1)
    assert ScamType.POLICE_IMPERSONATION not in summary.by_type
    assert summary.false_high == ["medium-01"]
    assert summary.false_warning == ["lookalike-01"]
    assert summary.confusion[(RiskLevel.HIGH, RiskLevel.MEDIUM)] == 1
    assert summary.assessed_by == {"rules": 1, "llm": 4}
    # Classifier verdicts only.
    assert summary.latencies == [0.5, 1.0, 2.0, 5.0]

    report = format_report(summary, budget=4)
    assert "1/4 over the 4 s budget" in report
    assert "Pending (quota or --limit): police-01" in report


def test_cache_round_trip_and_key(tmp_path: Path) -> None:
    path = tmp_path / "scam_eval" / "model.jsonl"
    first = result(BANK_1, "high", "bank_impersonation")
    append_cache(path, first)
    append_cache(path, result(BENIGN, "none", None))

    cache = load_cache(path)

    assert cache[cache_key(BANK_1)] == first
    assert len(cache) == 2
    # A changed situation gets a new key: its old verdict isn't reused.
    assert cache_key(case("bank-01", "high", "bank_impersonation", "Khác.")) not in cache


def test_rules_only_matches_layer_1_on_the_test_set() -> None:
    cases = load_cases()
    results = {c.id: rules_result(c) for c in cases}

    summary = summarize(cases, results)

    # SCAM-02's guarantees, seen through the report.
    assert summary.evaluated == len(cases) and summary.pending == []
    assert summary.false_high == []
    assert all(row.warned == row.cases for row in summary.by_type.values())
    assert set(summary.assessed_by) <= {"rules", "rules_only"}
