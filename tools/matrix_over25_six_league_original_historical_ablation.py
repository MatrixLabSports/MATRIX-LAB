"""Read-only original six-league enriched-vs-raw source substitution evidence.

The 2026-10-24 API-Football capture contains authentic historical canonical
inputs and historical raw match groups. This is a historical same-provider
ablation, NOT a cross-provider pair, new P_MATRIX, or prospective prediction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tools.matrix_over25_enriched_vs_group_parity import compare_cycle, DEFAULT_CYCLE

SIX = ("39", "61", "78", "135", "140", "239")
NAMES = {
    "39": "Premier League (Inglaterra)",
    "61": "Ligue 1 (Francia)",
    "78": "Bundesliga (Alemania)",
    "135": "Serie A (Italia)",
    "140": "LaLiga (Espana)",
    "239": "Primera A (Colombia)",
}
OUT = Path("evidence/football_world_inventory/MATRIX_OVER25_SIX_LEAGUE_CANONICAL_VS_RAW_HISTORICAL_LAST.json")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evaluate(cycle: Path = DEFAULT_CYCLE) -> dict:
    # An archived original manifest is necessary; no remote or current source
    # data are requested, nor can the archived cycle be silently replaced.
    manifest_path = cycle / "canonical_analysis" / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("ORIGINAL_CANONICAL_MANIFEST_MISSING")
    raw = manifest_path.read_bytes()
    original = json.loads(raw)
    if (original.get("provider") != "api_football"
        or original.get("status") != "PASS"
        or original.get("real_money") != "BLOCKED"
        or original.get("p_matrix_status") != "NOT_GENERATED"
        or original.get("model_probability_generated") is not False):
        raise ValueError("ORIGINAL_ARCHIVE_NOT_SAFE_RESEARCH_INPUT")
    six = []
    for league in SIX:
        raw_group = cycle / "history" / "raw" / f"league_{league}_season_2026.bin"
        if not raw_group.is_file():
            # A missing league is a visible blocker, never 0 unchanged rows.
            six.append({"original_league_id": league, "name": NAMES[league],
                        "status": "MISSING_ORIGINAL_RAW_GROUP",
                        "canonical_targets": None, "paired_targets": 0,
                        "probability_changed_targets": None,
                        "probability_identical_targets": None})
            continue
        evidence = compare_cycle(cycle, league)
        paired = evidence["paired_targets"]
        changed = evidence["probability_changed_targets"]
        same = evidence["probability_identical_targets"]
        if paired != changed + same:
            raise ValueError("HISTORICAL_ABLATION_COUNT_INCONSISTENT")
        rows = evidence["rows"]
        changed_rows = [x for x in rows if
            x.get("reference_status") == "PAIRED_ARCHIVED_REPLAY_ONLY"
            and not x.get("same_probability_with_group_only")]
        six.append({
            "original_league_id": league, "name": NAMES[league],
            "status": "HISTORICAL_SAME_PROVIDER_ABLATION_ONLY" if paired
                      else "HISTORICAL_NO_REPLAYABLE_PAIRS",
            "canonical_targets": evidence["canonical_targets"],
            "paired_targets": paired,
            "probability_changed_targets": changed,
            "probability_identical_targets": same,
            "blocked_targets": evidence["blocked_targets"],
            "maximum_probability_difference": evidence["maximum_probability_difference"],
            "raw_original_group_sha256": digest(raw_group.read_bytes()),
            "reference_canonical_bundle_sha256": evidence["reference_canonical_bundle_sha256"],
            "change_examples": [{
                "fixture_id": row["fixture_id"],
                "absolute_probability_delta": row["absolute_probability_delta"],
                "enriched_history_source": row.get("enriched_history_source")
            } for row in changed_rows[:5]],
        })
    paired_total = sum(x["paired_targets"] for x in six)
    changed_total = sum(x.get("probability_changed_targets") or 0 for x in six)
    missing = [x["original_league_id"] for x in six
               if x["status"] == "MISSING_ORIGINAL_RAW_GROUP"]
    return {
        "schema": "MATRIX_OVER25_SIX_LEAGUE_ORIGINAL_HISTORICAL_ABLATION_V1",
        "source_cycle": cycle.as_posix(),
        "original_manifest_sha256": digest(raw),
        "original_manifest_as_of_utc": original["analysis_as_of_utc"],
        "six_original_leagues": six,
        "source_group_missing_league_ids": missing,
        "historical_paired_rows": paired_total,
        "historical_probability_changed_rows": changed_total,
        "historical_substitution_equivalent_for_all_replayed": (
            paired_total > 0 and changed_total == 0 and not missing
        ),
        "historical_same_provider_only": True,
        "no_cross_provider_fixture_parity_certified": True,
        "historical_reconstruction_is_not_prospective_freeze": True,
        "original_official_p_matrix_restored": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cycle", type=Path, default=DEFAULT_CYCLE)
    p.add_argument("--out", type=Path, default=OUT)
    args = p.parse_args()
    if set(args.out.parts) & {"telegram", "daily_prematch_reports", "tennis_signals", "governance"}:
        raise SystemExit("HISTORICAL_ABLATION_CANNOT_WRITE_PRODUCTION")
    result = evaluate(args.cycle)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
                        + "\n", encoding="utf-8")
    print(json.dumps({
        "historical_paired_rows": result["historical_paired_rows"],
        "historical_probability_changed_rows": result["historical_probability_changed_rows"],
        "source_group_missing_league_ids": result["source_group_missing_league_ids"],
        "telegram_signal_authorized": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
