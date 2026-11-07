"""Offline-only independent source readiness assessment. No network, no Telegram."""
import json
from datetime import datetime, timezone
from pathlib import Path


def assess(data, now=None):
    now = now or datetime.now(timezone.utc)
    blockers = []
    discovery = data.get("discovery") or {}
    quote = data.get("quote") or {}
    sharp = data.get("sharp") or {}
    if discovery.get("source_order") != ["SOFASCORE", "FLASHSCORE"]:
        blockers.append("DISCOVERY_ORDER_UNVERIFIED")
    if discovery.get("fixture_verified") is not True or not discovery.get("evidence_path"):
        blockers.append("FIXTURE_EVIDENCE_MISSING")
    if quote.get("verified") is not True or not quote.get("evidence_path"):
        blockers.append("BOOK_QUOTE_EVIDENCE_MISSING")
    if quote.get("colombia_authorized") is not True:
        blockers.append("BOOK_NOT_AUTHORIZED")
    if quote.get("market") != "TOTAL_GOALS_OVER_UNDER" or quote.get("selection") != "OVER_2_5":
        blockers.append("MARKET_NOT_PROMOTED")
    for key in ("fixture_id", "bookmaker", "decimal_odds", "p_matrix", "kickoff_utc"):
        if quote.get(key) in (None, ""):
            blockers.append("QUOTE_MISSING_" + key)
    if sharp.get("verified") is not True or not sharp.get("evidence_path"):
        blockers.append("SHARP_EVIDENCE_MISSING")
    if sharp.get("fixture_id") != quote.get("fixture_id"):
        blockers.append("SHARP_FIXTURE_MISMATCH")
    for label, item in (("BOOK", quote), ("SHARP", sharp)):
        try:
            timestamp = datetime.fromisoformat(item["updated_at_utc"].replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("naive")
            age = (now - timestamp.astimezone(timezone.utc)).total_seconds()
            if not 0 <= age <= 120:
                blockers.append(label + "_STALE")
        except (ValueError, TypeError, KeyError, AttributeError):
            blockers.append(label + "_TIMESTAMP_INVALID")
    try:
        kickoff = datetime.fromisoformat(quote["kickoff_utc"].replace("Z", "+00:00"))
        if kickoff.tzinfo is None or kickoff <= now:
            blockers.append("KICKOFF_NOT_FUTURE")
    except (ValueError, TypeError, KeyError, AttributeError):
        blockers.append("KICKOFF_INVALID")
    try:
        odds, probability = float(quote["decimal_odds"]), float(quote["p_matrix"])
        import math
        if not (math.isfinite(odds) and math.isfinite(probability) and odds > 1.5 and 0.6 <= probability <= 1 and odds * probability - 1 >= 0.05):
            blockers.append("PRICE_PROBABILITY_OR_EV_GATE")
    except (ValueError, TypeError, KeyError):
        blockers.append("PRICE_PROBABILITY_INVALID")
    if data.get("governance_pass") is not True or data.get("correlation_pass") is not True:
        blockers.append("GOVERNANCE_OR_CORRELATION_UNVERIFIED")
    return {
        "schema": "MATRIX_INDEPENDENT_SOURCE_READINESS_V1",
        "status": "SHADOW_READINESS_ONLY" if not blockers else "BLOCKED",
        "blockers": sorted(set(blockers)),
        "paid_api_calls": 0,
        "independent_api_calls": 0,
        "telegram_calls": 0,
        "telegram_delivery_certified": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "limitation": "Input evidence fields are not independently authenticated; this never authorizes sending.",
    }


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.input.resolve() == a.output.resolve():
        raise SystemExit("INPUT_OUTPUT_COLLISION")
    data = json.loads(a.input.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("INPUT_NOT_OBJECT")
    result = assess(data)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
