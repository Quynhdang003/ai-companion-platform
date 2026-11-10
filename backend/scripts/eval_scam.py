"""Evaluate the Scam Risk Engine on the labelled test set (`backend/data/scam_eval/`).

Run from backend/:
- `uv run python -m scripts.eval_scam --rules-only`: layer 1 alone, no DB and no Gemini.
- `uv run python -m scripts.eval_scam [--limit N]`: the whole engine. Needs the dev DB with
  the scam patterns seeded (`scripts.seed_scam_patterns`) and GEMINI_API_KEY; uses
  GEMINI_SCAM_MODEL. `--limit` caps the classifier calls of this run.

The free tier allows about 20 requests a day per model, fewer than the cases that reach the
classifier. Classifier verdicts are cached in `backend/.cache/scam_eval/<model>.jsonl`, keyed
by the situation and PROMPT_VERSION, so a run stopped by the quota goes on where it left
off the next day. Only real verdicts are cached: errors and timeouts are retried.

The classifier gets a generous timeout here, to measure the model; the report counts how
many verdicts took longer than the in-call budget (SCAM_CHECK_TIMEOUT_SECONDS).
"""

import argparse
import asyncio
import hashlib
import statistics
import sys
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.llm.client import get_scam_llm_client
from app.llm.prompts.scam_classification import PROMPT_VERSION
from app.models import RiskLevel, ScamType
from app.services.scam.engine import AssessedBy, FallbackReason, assess
from app.services.scam.rules import assess_rules
from scripts.scam_cases import ScamCase, load_cases

CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "scam_eval"
EVAL_TIMEOUT_SECONDS = 30.0
RULES_ONLY = "rules_only"


class CaseResult(BaseModel):
    case_id: str
    key: str
    level: RiskLevel
    scam_type: ScamType | None
    # An `AssessedBy` value, or RULES_ONLY for a non-decisive case in --rules-only.
    assessed_by: str
    fallback_reason: str | None = None
    latency_seconds: float = 0.0
    reason: str | None = None


def cache_key(case: ScamCase) -> str:
    """Changes when the situation or the prompt changes, so stale verdicts aren't reused."""
    digest = hashlib.sha256(f"{PROMPT_VERSION}\n{case.situation}".encode()).hexdigest()
    return digest[:16]


def load_cache(path: Path) -> dict[str, CaseResult]:
    if not path.exists():
        return {}
    results = (
        CaseResult.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    return {result.key: result for result in results}


def append_cache(path: Path, result: CaseResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(result.model_dump_json() + "\n")


def rules_result(case: ScamCase) -> CaseResult:
    rules = assess_rules(case.situation)
    medium_or_more = rules.level.rank >= RiskLevel.MEDIUM.rank
    return CaseResult(
        case_id=case.id,
        key=cache_key(case),
        level=rules.level,
        scam_type=rules.scam_type if medium_or_more else None,
        assessed_by="rules" if rules.decisive else RULES_ONLY,
    )


# --- report ----------------------------------------------------------------------------


@dataclass(frozen=True)
class TypeRow:
    cases: int
    high: int  # flagged high
    warned: int  # flagged at least medium: the caller hears a warning
    right_type: int  # flagged at least medium with the labelled type


@dataclass(frozen=True)
class Summary:
    evaluated: int
    pending: list[str]
    by_type: dict[ScamType, TypeRow]
    # (expected, got) -> count
    confusion: Counter[tuple[RiskLevel, RiskLevel]]
    # Not labelled high, flagged high.
    false_high: list[str]
    # Labelled none or low, flagged at least medium.
    false_warning: list[str]
    assessed_by: Counter[str]
    fallback_reasons: Counter[str]
    # Classifier verdicts only.
    latencies: list[float]


def summarize(cases: Sequence[ScamCase], results: Mapping[str, CaseResult]) -> Summary:
    """`results` maps case ids to results; cases without one are pending."""
    by_type: dict[ScamType, TypeRow] = {}
    confusion: Counter[tuple[RiskLevel, RiskLevel]] = Counter()
    false_high: list[str] = []
    false_warning: list[str] = []
    pending: list[str] = []
    for case in cases:
        result = results.get(case.id)
        if result is None:
            pending.append(case.id)
            continue
        confusion[(case.level, result.level)] += 1
        warned = result.level.rank >= RiskLevel.MEDIUM.rank
        if case.level is RiskLevel.HIGH and case.scam_type is not None:
            row = by_type.get(case.scam_type, TypeRow(0, 0, 0, 0))
            by_type[case.scam_type] = TypeRow(
                cases=row.cases + 1,
                high=row.high + (result.level is RiskLevel.HIGH),
                warned=row.warned + warned,
                right_type=row.right_type + (warned and result.scam_type is case.scam_type),
            )
        if case.level is not RiskLevel.HIGH and result.level is RiskLevel.HIGH:
            false_high.append(case.id)
        if case.level.rank <= RiskLevel.LOW.rank and warned:
            false_warning.append(case.id)

    done = [results[case.id] for case in cases if case.id in results]
    return Summary(
        evaluated=len(done),
        pending=pending,
        by_type={t: by_type[t] for t in ScamType if t in by_type},
        confusion=confusion,
        false_high=false_high,
        false_warning=false_warning,
        assessed_by=Counter(result.assessed_by for result in done),
        fallback_reasons=Counter(r.fallback_reason for r in done if r.fallback_reason),
        latencies=sorted(r.latency_seconds for r in done if r.assessed_by == "llm"),
    )


def format_report(summary: Summary, budget: float) -> str:
    lines = [f"Evaluated {summary.evaluated} cases, {len(summary.pending)} pending."]
    lines += ["", "High-risk cases by type: flagged high / warned (>= medium) / right type"]
    rows = list(summary.by_type.values())
    total = TypeRow(
        cases=sum(row.cases for row in rows),
        high=sum(row.high for row in rows),
        warned=sum(row.warned for row in rows),
        right_type=sum(row.right_type for row in rows),
    )
    for name, row in [*((t.value, r) for t, r in summary.by_type.items()), ("all", total)]:
        lines.append(
            f"  {name:<24} {row.high}/{row.cases}  {row.warned}/{row.cases}"
            f"  {row.right_type}/{row.cases}"
        )

    levels = list(RiskLevel)
    lines += ["", "Levels: expected (rows) x got (columns)"]
    lines.append("  " + " " * 8 + "".join(f"{level.value:>8}" for level in levels))
    for expected in levels:
        counts = "".join(f"{summary.confusion[(expected, got)]:>8}" for got in levels)
        lines.append(f"  {expected.value:<8}{counts}")

    lines += [
        "",
        f"Flagged high but not labelled high: {_ids(summary.false_high)}",
        f"Labelled none/low but warned: {_ids(summary.false_warning)}",
        "",
        "Assessed by: " + ", ".join(f"{k} {v}" for k, v in sorted(summary.assessed_by.items())),
    ]
    if summary.fallback_reasons:
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(summary.fallback_reasons.items()))
        lines.append(f"Fallback reasons: {reasons}")
    if summary.latencies:
        latencies = summary.latencies
        p90 = latencies[min(len(latencies) - 1, int(0.9 * len(latencies)))]
        over = sum(latency > budget for latency in latencies)
        lines.append(
            f"Classifier latency: p50 {statistics.median(latencies):.2f} s, p90 {p90:.2f} s, "
            f"max {latencies[-1]:.2f} s; {over}/{len(latencies)} over the {budget:g} s budget"
        )
    if summary.pending:
        lines += ["", f"Pending (quota or --limit): {_ids(summary.pending)}"]
    return "\n".join(lines)


def _ids(ids: Sequence[str]) -> str:
    return ", ".join(ids) if ids else "none"


# --- run -------------------------------------------------------------------------------


async def run_engine(cases: Sequence[ScamCase], limit: int | None) -> dict[str, CaseResult]:
    settings = get_settings()
    if not settings.gemini_api_key:
        sys.exit("GEMINI_API_KEY is not set: use --rules-only, or set it in backend/.env")
    cache_path = CACHE_DIR / f"{settings.gemini_scam_model}.jsonl"
    cache = load_cache(cache_path)
    llm = get_scam_llm_client()
    results: dict[str, CaseResult] = {}
    calls = 0
    async with SessionLocal() as db:
        for case in cases:
            rules = rules_result(case)
            if rules.assessed_by == "rules":
                results[case.id] = rules  # decisive: the engine wouldn't call the classifier
                continue
            key = cache_key(case)
            if key in cache:
                results[case.id] = cache[key].model_copy(update={"case_id": case.id})
                continue
            if limit is not None and calls >= limit:
                continue
            calls += 1
            started = time.monotonic()
            assessment = await assess(db, llm, case.situation, timeout=EVAL_TIMEOUT_SECONDS)
            latency = time.monotonic() - started
            if assessment.fallback_reason is FallbackReason.RATE_LIMITED:
                print(f"Rate limited at {case.id}: run again later to go on.", file=sys.stderr)
                break
            result = CaseResult(
                case_id=case.id,
                key=key,
                level=assessment.level,
                scam_type=assessment.scam_type,
                assessed_by=assessment.assessed_by.value,
                fallback_reason=(
                    assessment.fallback_reason.value if assessment.fallback_reason else None
                ),
                latency_seconds=round(latency, 3),
                reason=assessment.reason,
            )
            results[case.id] = result
            if assessment.assessed_by is AssessedBy.LLM:
                append_cache(cache_path, result)
            print(
                f"{case.id:<16} expected {case.level.value:<6} got {result.level.value:<6} "
                f"{result.scam_type.value if result.scam_type else '-':<24} "
                f"{result.assessed_by} {latency:.2f} s",
                file=sys.stderr,
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rules-only", action="store_true", help="layer 1 alone")
    parser.add_argument("--limit", type=int, help="at most N classifier calls this run")
    args = parser.parse_args()

    cases = load_cases()
    if args.rules_only:
        results = {case.id: rules_result(case) for case in cases}
    else:
        results = asyncio.run(run_engine(cases, args.limit))
    budget = get_settings().scam_check_timeout_seconds
    print(format_report(summarize(cases, results), budget))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    main()
