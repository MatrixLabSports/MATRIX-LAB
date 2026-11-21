"""Fail-closed certification of browser-observed tennis calendar evidence.

The observation record is not a fixture snapshot and must never be used to
manufacture UTC kickoff, surface, probabilities, odds or Telegram candidates.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

SCHEMA = "MATRIX_OPERA_TENNIS_CALENDAR_CROSSCHECK_V1"
RESULT_SCHEMA = "MATRIX_TENNIS_CALENDAR_EVIDENCE_GATE_V1"


def evaluate(record: dict) -> dict:
    if record.get("schema") != SCHEMA:
        raise ValueError("UNTRUSTED_TENNIS_OBSERVATION_SCHEMA")
    sources = record.get("sources", [])
    names = record.get("observed_name_matches", [])
    sofa = record.get("sofascore_observed_matches", [])
    flash = record.get("flashscore_observed_match_ids", [])
    required_sources = {"SofaScore", "Flashscore"}
    source_names = {x.get("provider") for x in sources if isinstance(x, dict)}
    pairs_observed = (
        source_names == required_sources
        and isinstance(names, list) and isinstance(sofa, list) and isinstance(flash, list)
        and len(names) == len(sofa) == len(flash) == 5
        and len({x.get("id") for x in sofa if isinstance(x, dict)}) == 5
        and len({x.get("mid") for x in flash if isinstance(x, dict)}) == 5
    )
    # No trust escalation based on caller-declared verification flags alone.
    return {
        "schema": RESULT_SCHEMA,
        "status": "OBSERVED_ONLY_NOT_CERTIFIED",
        "cross_provider_observations_present": pairs_observed,
        "observed_count": len(names) if pairs_observed else 0,
        "utc_kickoff_certified": False,
        "surface_certified": False,
        "canonical_fixture_export_authorized": False,
        "probability_generation_authorized": False,
        "telegram_signals_authorized": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
        "reasons": ["DISPLAY_TIME_TIMEZONE_UNVERIFIED", "SURFACE_UNVERIFIED",
                    "CROSS_PROVIDER_MATCH_IDENTITY_NOT_INDEPENDENTLY_CERTIFIED"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    if any(p in out.parts for p in ("daily_prematch_reports", "tennis_signals")):
        raise SystemExit("OBSERVATION_GATE_CANNOT_WRITE_SIGNAL_PATH")
    record = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = evaluate(record)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
