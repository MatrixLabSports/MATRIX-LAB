"""Brazil Serie A: compare archived paid-era history to authenticated free history.

Historical verification only. The immutable original calibrated model and
its CANONICAL_ENRICHED_PIT inputs are NOT re-created or promoted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.matrix_independent_over25_historical_parity import (
    utc, parse_archive, parse_free, compare, compare_raw_features,
)

ARCHIVE = Path("evidence/api_football/prospective_daily/2026-10-26/20261026T215729Z/history/raw/league_71_season_2026.bin")
CYCLE = Path("evidence/api_football/prospective_daily/2026-10-26/20261026T215729Z/cycle_summary.json")
ENDPOINT = "https://api.football-data.org/v4/competitions/BSA/matches"
MAX_BYTES = 3000000
API_LEAGUE = 71
FREE_LEAGUE = 2013


def inspect(token: str, *, archive: Path = ARCHIVE, cycle: Path = CYCLE,
            opener=urlopen) -> dict:
    result = {
        "schema": "MATRIX_BRAZIL_ORIGINAL_RAW_FEATURE_PARITY_V1",
        "reference_source": "ARCHIVED_API_FOOTBALL",
        "source": "FOOTBALL_DATA_ORG",
        "reference_league_id": API_LEAGUE,
        "source_league_id": FREE_LEAGUE,
        "historical_analysis_only": True,
        "status": "BLOCKED_PARITY_UNVERIFIED",
        "network_calls": 0,
        "historical_goal_result_concordance_verified": False,
        "original_calibrated_feature_equivalence_verified": False,
        "canonical_enriched_pit_equivalence_verified": False,
        "all_six_leagues_equivalence_verified": False,
        "model_parameters_mutated": False,
        "signal_generation_authorized": False,
        "telegram_messages_sent": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    try:
        raw_bytes = archive.read_bytes()
        cycle_json = json.loads(cycle.read_text(encoding="utf-8"))
        if cycle_json.get("status") != "PASS":
            raise ValueError("ARCHIVED_REFERENCE_NOT_PASS")
        cutoff = utc(cycle_json["finished_at_utc"])
        api_raw = json.loads(raw_bytes.decode("utf-8"))
        archive_rows = parse_archive(
            api_raw, cutoff, archived_league_id=API_LEAGUE,
        )
        result["reference_fixture_count"] = len(archive_rows)
        result["reference_raw_sha256"] = hashlib.sha256(raw_bytes).hexdigest()
        result["reference_raw_path"] = str(archive)
        result["reference_cycle_cutoff_utc"] = cutoff.isoformat()
        if not token.strip():
            result["status"] = "BLOCKED_MISSING_FREE_PROVIDER_KEY"
            return result
        req = Request(ENDPOINT, headers={
            "X-Auth-Token": token.strip(), "Accept": "application/json",
        })
        result["network_calls"] = 1
        with opener(req, timeout=25) as response:
            response_status = int(response.status)
            body = response.read(MAX_BYTES + 1)
        result["free_provider_http_status"] = response_status
        result["free_response_sha256"] = hashlib.sha256(body).hexdigest()
        if response_status != 200 or len(body) > MAX_BYTES:
            result["status"] = "BLOCKED_FREE_PROVIDER_HTTP_OR_SIZE"
            return result
        free_raw = json.loads(body.decode("utf-8"))
        free_rows = parse_free(
            free_raw, cutoff, source_league_id=FREE_LEAGUE,
        )
        result["free_fixture_count"] = len(free_rows)
        pairs = compare(archive_rows, free_rows)
        matched = pairs["matches"]
        result["matched_exact_result_count"] = len(matched)
        result["score_disagreement_count"] = len(pairs["score_disagreements"])
        result["unmatched_free_count"] = len(pairs["unmatched_free"])
        result["ambiguous_count"] = len(pairs["ambiguous"])
        result["matched_result_examples"] = matched[:12]
        result["raw_group_feature_parity"] = compare_raw_features(
            api_raw, free_raw, matched, cutoff,
            source_league_id=FREE_LEAGUE,
            archived_api_league_id=API_LEAGUE,
        )
        results_match = (
            len(matched) >= 20
            and len(pairs["score_disagreements"]) == 0
            and len(pairs["ambiguous"]) == 0
            and len(matched) / max(1, len(free_rows)) >= 0.7
        )
        result["historical_goal_result_concordance_verified"] = results_match
        result["status"] = (
            "PASS_BRAZIL_HISTORICAL_SCORE_CONCORDANCE_ONLY"
            if results_match else "BLOCKED_BRAZIL_SCORE_PARITY_INCOMPLETE"
        )
    except (HTTPError, URLError, TimeoutError, OSError, ValueError,
            KeyError, TypeError, AssertionError, UnicodeError) as exc:
        result["status"] = "BLOCKED_BRAZIL_PARITY_PROBE_ERROR"
        result["error_type"] = type(exc).__name__
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    a = parser.parse_args()
    r = inspect(os.environ.get("FOOTBALL_DATA_ORG_TOKEN", ""))
    if "daily_prematch_reports" in a.out.parts or "tennis_signals" in a.out.parts:
        raise SystemExit("RESEARCH_AUDIT_CANNOT_CREATE_TELEGRAM_CANDIDATES")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(
        r, ensure_ascii=False, sort_keys=True, indent=2,
    ) + "\n", encoding="utf-8")
    print(json.dumps({
        k: r.get(k) for k in (
            "status", "network_calls", "matched_exact_result_count",
            "historical_goal_result_concordance_verified",
            "original_calibrated_feature_equivalence_verified",
            "signal_generation_authorized",
        )
    }, sort_keys=True))


if __name__ == "__main__":
    main()
