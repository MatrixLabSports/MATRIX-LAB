"""Connect authentic prelabel research predictions to MATRIX Híbrida Élite.

This is NOT the formal hybrid laboratory input: the original provider's
certified p_MATRIX is absent. Only two distinct independent research tracks
may be compared once separate postmatch, SHA-certified results exist.

Inputs: SHA-bound frozen forecasts and their full, authentic source envelopes.
Never fetch live data, use outcomes, change original calibration or send bets.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from tools.matrix_independent_free_poisson_oos import safe_row, stamp

SCHEMA = "MATRIX_HYBRID_ELITE_RESEARCH_PRELABEL_PAIRS_V1"
RESEARCH_ROOT = Path("evidence/football_research_freezes")
POISSON_ROOT = Path("evidence/football_world_inventory")
MIN_SOURCE = 100
MAX_BYTES = 24_000_000


def require(condition: bool, reason: str):
    if not condition:
        raise ValueError(reason)


def file_bytes(root: Path, raw_path: str, expected_sha: str) -> bytes:
    rel = Path(raw_path)
    require(not rel.is_absolute() and ".." not in rel.parts,
            "UNTRUSTED_SOURCE_FILE_PATH")
    target = root / rel
    require(target.is_file(), "SOURCE_FILE_MISSING")
    raw = target.read_bytes()
    require(MIN_SOURCE <= len(raw) <= MAX_BYTES, "SOURCE_BYTES_OUT_OF_BOUNDS")
    require(hashlib.sha256(raw).hexdigest() == expected_sha,
            "SOURCE_BYTES_SHA_MISMATCH")
    return raw


def source_envelope(root: Path, original: dict, memo: dict):
    ps = original["source_shadow_file_path"]
    pi = original["source_intake_file_path"]
    k = (ps, pi)
    if k not in memo:
        shadow = json.loads(file_bytes(root, ps, original["source_shadow_file_sha256"]))
        intake = json.loads(file_bytes(root, pi, original["source_intake_file_sha256"]))
        require(shadow.get("schema") == "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
                "SOURCE_SHADOW_SCHEMA_MISMATCH")
        require(intake.get("schema") == "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1",
                "SOURCE_INTAKE_SCHEMA_MISMATCH")
        require(shadow.get("real_money") == intake.get("real_money") == "BLOCKED",
                "SOURCE_REAL_MONEY_MISMATCH")
        require(shadow.get("market_signal_authorized") is False and
                intake.get("signal_generation_authorized") is False,
                "SOURCE_PROMOTION_NOT_ALLOWED")
        memo[k] = shadow, intake
    return memo[k]


def check_one(root: Path, poisson_path: Path, now: datetime, memo: dict) -> dict:
    po, kickoff = safe_row(poisson_path, now)
    fid = str(po["fixture_id"])
    require(fid.isdecimal(), "NON_NUMERIC_PROVIDER_FIXTURE_ID")
    day = poisson_path.parent.parent.name
    require(day == kickoff.astimezone(__import__("zoneinfo").ZoneInfo("America/Bogota")).date().isoformat(),
            "FORECAST_TARGET_DAY_INCONSISTENT")
    originals = list((root / RESEARCH_ROOT / day).glob(fid + "_*.json"))
    candidates = []
    for path in originals:
        if "_result_" in path.name:
            continue
        original = json.loads(path.read_bytes())
        if original.get("schema") != "MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1":
            continue
        if original.get("source_snapshot_sha256") != po["history_raw_sha256"]:
            continue
        if (str(original.get("provider_fixture_id")) != fid
            or str(original.get("provider_competition_id")) != str(po["provider_competition_id"])):
            continue
        if (original.get("provider") != "FOOTBALL_DATA_ORG"
            or original.get("real_money") != "BLOCKED"
            or original.get("production_p_matrix_authorized") is not False
            or original.get("telegram_signal_authorized") is not False
            or original.get("frozen_calibrated_model_parameters_mutated") is not False):
            raise ValueError("ORIGINAL_RESEARCH_PRODUCTION_SCOPE_VIOLATION")
        sealed = stamp(original["sealed_at_utc"])
        require(sealed < kickoff and sealed <= stamp(po["forecast_frozen_at_utc"]),
                "ORIGINAL_RESEARCH_NOT_FROZEN_BEFORE_COMPARISON")
        require(stamp(original["history_captured_at_utc"]) < sealed,
                "ORIGINAL_RESEARCH_HISTORY_AFTER_FREEZE")
        require(stamp(original["model_calculated_at_utc"]) < sealed,
                "ORIGINAL_RESEARCH_FORMULA_AFTER_FREEZE")
        require(stamp(original["kickoff_utc"]) == kickoff, "ORIGINAL_KICKOFF_MISMATCH")
        p = original.get("research_probability_over25")
        require(type(p) in (float, int) and math.isfinite(p) and 0 < p < 1,
                "ORIGINAL_RESEARCH_PROBABILITY_INVALID")
        candidates.append((sealed, path, original))
    require(candidates, "NO_SAME_RAW_HISTORY_ORIGINAL_RESEARCH_FORECAST")
    candidates.sort(key=lambda row: row[0], reverse=True)
    if len(candidates) > 1:
        require(candidates[0][0] != candidates[1][0],
                "ORIGINAL_RESEARCH_AMBIGUOUS_SAME_CAPTURE_TIME")
    _, original_path, original = candidates[0]
    shadow, intake = source_envelope(root, original, memo)
    require(intake.get("target_date_bogota") == shadow.get("target_date_bogota") == day,
            "SOURCE_DAY_INCONSISTENT")
    group = (shadow.get("authenticated_raw_group_replay_evidence") or {}).get(
        str(po["provider_competition_id"]))
    require(isinstance(group, dict), "SOURCE_LEAGUE_HISTORY_MISSING")
    require(group.get("source_payload_sha256") == po["history_raw_sha256"],
            "SOURCE_GROUP_HISTORY_SHA_MISMATCH")
    raw_history = base64.b64decode(group["response_base64"], validate=True)
    require(hashlib.sha256(raw_history).hexdigest() == po["history_raw_sha256"],
            "SOURCE_AUTHENTICATED_HISTORY_BYTES_MISMATCH")
    require(stamp(group["observed_at_utc"]) == stamp(po["history_observed_at_utc"]),
            "SOURCE_POISSON_HISTORY_TIME_MISMATCH")
    require(stamp(group["observed_at_utc"]) < kickoff,
            "SOURCE_HISTORY_AFTER_KICKOFF")
    matches = [r for r in intake.get("fixtures", [])
               if str(r.get("source_fixture_id")) == fid]
    require(len(matches) == 1, "SOURCE_INTAKE_FIXTURE_NOT_UNIQUE")
    source = matches[0]
    require(str(source.get("source_competition_id")) == str(po["provider_competition_id"])
            and stamp(source["kickoff_utc"]) == kickoff
            and source["home"] == po["home"]
            and source["away"] == po["away"]
            and source.get("api_football_fixture_id") is None,
            "RESEARCH_PROVIDER_IDENTITIES_NOT_EQUAL")
    return {
        "physical_event_id": fid,
        "source_provider": "FOOTBALL_DATA_ORG",
        "lane": "FOOTBALL_OVER25",
        "competition_id": str(po["provider_competition_id"]),
        "event_start_at_utc": kickoff.isoformat(),
        "original_formula_research_p": original["research_probability_over25"],
        "independent_free_poisson_p": po["research_probability_over25"],
        "original_formula_research_frozen_at_utc": original["sealed_at_utc"],
        "independent_poisson_frozen_at_utc": po["forecast_frozen_at_utc"],
        "original_freeze_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
        "original_freeze_path": original_path.relative_to(root).as_posix(),
        "poisson_freeze_sha256": hashlib.sha256(poisson_path.read_bytes()).hexdigest(),
        "poisson_freeze_path": poisson_path.relative_to(root).as_posix(),
        "common_history_raw_sha256": po["history_raw_sha256"],
        "original_source_intake_sha256": original["source_intake_file_sha256"],
        "original_source_shadow_sha256": original["source_shadow_file_sha256"],
        "same_authenticated_input_evidence": True,
        "postmatch_outcome_included": False,
        "original_official_p_matrix_certified": False,
        "formal_hybrid_lab_admission_authorized": False,
    }


def prepare(root: Path, now: datetime | None = None, day: str | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    require(now.utcoffset() is not None, "UTC_CLOCK_REQUIRED")
    now = now.astimezone(timezone.utc)
    forecasts = sorted((root / POISSON_ROOT).glob(
        (day if day else "20??-??-??") + "/MATRIX_FREE_POISSON_V1_IMMUTABLE/*.json"))
    pairs, rejected, seen = [], [], set()
    memo = {}
    for p in forecasts:
        try:
            entry = check_one(root, p, now, memo)
            key = (entry["lane"], entry["physical_event_id"])
            require(key not in seen, "DUPLICATE_CANDIDATE_PHYSICAL_EVENT")
            seen.add(key)
            pairs.append(entry)
        except (OSError, KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"path": p.relative_to(root).as_posix(),
                             "reason": str(exc)[:140]})
    return {
        "schema": SCHEMA,
        "status": "SHA_BOUND_PRELABEL_RESEARCH_PAIRING_NO_HYBRID_PROMOTION",
        "generated_at_utc": now.isoformat(),
        "provider": "FOOTBALL_DATA_ORG",
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "recovered_research_pair_count": len(pairs),
        "rejected_research_pair_count": len(rejected),
        "prelabel_research_pairs": pairs,
        "rejected": rejected,
        "existing_official_original_p_matrix_pairs": 0,
        "formal_hybrid_elite_lab_rows_admitted": 0,
        "independently_certified_postmatch_pairs_in_this_prelabeled_receipt": 0,
        "original_model_parameters_mutated": False,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "production_p_matrix_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--day", default="2026-11-21")
    p.add_argument("--out", type=Path, default=Path(
        "evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json"))
    a = p.parse_args()
    banned = {"notifications", "telegram", "daily_prematch_reports", "tennis_signals"}
    require(not (banned & set(a.out.parts)), "HYBRID_RESEARCH_CANNOT_WRITE_PRODUCTION")
    result = prepare(a.root, day=a.day)
    target = a.out if a.out.is_absolute() else a.root / a.out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"research_pairs": result["recovered_research_pair_count"],
                      "rejected": result["rejected_research_pair_count"],
                      "official_hybrid_rows": 0, "real_money": "BLOCKED"}, sort_keys=True))


if __name__ == "__main__":
    main()
