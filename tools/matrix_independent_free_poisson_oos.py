"""Strict post-kickoff scorecard for the isolated free-source Poisson challenger.

Joins immutable independent Poisson pre-match freezes to real football-data.org
result bytes already recorded and SHA-bound by MATRIX's research settlement.
No score is read while a match is future; no calibration refit or bet promotion.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SOURCE = Path("evidence/football_world_inventory")
OUT = Path("evidence/football_world_inventory/MATRIX_FREE_POISSON_OOS_SCORECARD_LAST.json")
RESULTS = Path("evidence/football_research_freezes")
P_MODEL = "MATRIX_FREE_POISSON_TEAM_V1"


def stamp(token):
    v = datetime.fromisoformat(str(token).replace("Z", "+00:00"))
    if v.utcoffset() is None:
        raise ValueError("UNAWARE_SOURCE_TIMESTAMP")
    return v.astimezone(timezone.utc)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe_row(p: Path, now: datetime):
    j = json.loads(p.read_bytes())
    if (j.get("schema") != "MATRIX_FREE_POISSON_PROSPECTIVE_RESEARCH_V1"
        or j.get("model_id") != P_MODEL
        or j.get("provider") != "FOOTBALL_DATA_ORG"
        or j.get("real_money") != "BLOCKED"
        or j.get("p_matrix_authorized") is not False
        or j.get("telegram_signal_authorized") is not False):
        raise ValueError("FREE_POISSON_FREEZE_UNTRUSTED")
    kickoff = stamp(j["kickoff_utc"])
    frozen = stamp(j["forecast_frozen_at_utc"])
    observed = stamp(j["history_observed_at_utc"])
    if not observed <= frozen < kickoff:
        raise ValueError("FREE_POISSON_NOT_PROSPECTIVE")
    if frozen > now:
        raise ValueError("FREE_POISSON_FUTURE_FORECAST")
    if not isinstance(j.get("history_raw_sha256"), str) or len(j["history_raw_sha256"]) != 64:
        raise ValueError("FREE_POISSON_SOURCE_SHA_INVALID")
    prob = j["research_probability_over25"]
    if type(prob) not in (int, float) or not math.isfinite(prob) or not 0 < prob < 1:
        raise ValueError("FREE_POISSON_PROB_INVALID")
    return j, kickoff


def final_result(root: Path, po: dict, now: datetime):
    fid = str(po["fixture_id"])
    # Result partitions can differ from UTC kickoff date around midnight.
    # Search immutable research archives by provider ID; then strictly verify
    # identity, competition, kickoff, source bytes and original forecast.
    target = root / RESULTS
    candidates = sorted(target.glob("20??-??-??/" + fid + "_result_*.json"))
    if len(candidates) == 0:
        return None
    if len(candidates) != 1:
        raise ValueError("DUPLICATE_OR_AMBIGUOUS_PROVIDER_FINAL_RESULT")
    rp = candidates[0]
    result = json.loads(rp.read_bytes())
    if (result.get("schema") != "MATRIX_INDEPENDENT_OVER25_SETTLED_RESEARCH_V1"
        or result.get("real_money") != "BLOCKED"
        or result.get("telegram_signal_authorized") is not False
        or str(result["fixture_id"]) != fid
        or str(result["competition_id"]) != str(po["provider_competition_id"])
        or stamp(result["kickoff_utc"]) != stamp(po["kickoff_utc"])
        or not stamp(result["forecast_frozen_at_utc"]) < stamp(result["kickoff_utc"])
        or not stamp(result["kickoff_utc"]) < stamp(result["result_observed_at_utc"]) <= now):
        raise ValueError("INDEPENDENT_FINAL_RESULT_PROVENANCE_INVALID")
    raw_path = rp.parent / "sources" / (str(result["raw_result_sha256"]) + ".json")
    if not raw_path.is_file() or sha(raw_path) != result["raw_result_sha256"]:
        raise ValueError("FINAL_RESULT_SOURCE_SHA_INVALID")
    final = json.loads(raw_path.read_bytes())
    goals = (final.get("score") or {}).get("fullTime") or {}
    hg, ag = goals.get("home"), goals.get("away")
    if (str(final.get("id")) != fid or final.get("status") != "FINISHED"
        or type(hg) is not int or type(ag) is not int or hg < 0 or ag < 0
        or (hg, ag) != (result["home_goals"], result["away_goals"])
        or int(hg + ag > 2) != result.get("over25_outcome")):
        raise ValueError("FINAL_SCORE_NOT_AUTHENTIC")
    if final.get("lastUpdated") and stamp(final["lastUpdated"]) > now:
        raise ValueError("RESULT_PROVIDER_LAST_UPDATE_IN_FUTURE")
    # Require exact sealed original forecast SHA, not an arbitrary result
    # JSON claiming to be an original model probability.
    forecasts = [
        x for x in rp.parent.glob(fid + "_*.json")
        if "_result_" not in x.name and sha(x) == result.get("forecast_sha256")
    ]
    if len(forecasts) != 1:
        raise ValueError("ORIGINAL_PREMATCH_FORECAST_SHA_MISSING_OR_DUPLICATE")
    original = json.loads(forecasts[0].read_bytes())
    if (original.get("schema") != "MATRIX_INDEPENDENT_OVER25_PREMATCH_IMMUTABLE_FREEZE_V1"
        or original.get("provider") != "FOOTBALL_DATA_ORG"
        or original.get("real_money") != "BLOCKED"
        or original.get("telegram_signal_authorized") is not False
        or str(original.get("provider_fixture_id")) != fid
        or str(original.get("provider_competition_id")) != str(po["provider_competition_id"])
        or stamp(original["kickoff_utc"]) != stamp(po["kickoff_utc"])
        or not stamp(original["sealed_at_utc"]) < stamp(original["kickoff_utc"])
        or original.get("research_probability_over25") != result.get("research_probability_over25")):
        raise ValueError("ORIGINAL_FORECAST_IDENTITY_OR_PROBABILITY_INVALID")
    # The source fixture and team ids are distinct from API-Football ids.
    source_path = root / str(original["source_intake_file_path"])
    if not source_path.is_file() or sha(source_path) != original.get("source_intake_file_sha256"):
        raise ValueError("ORIGINAL_INTAKE_RAW_SHA_INVALID")
    source_intake = json.loads(source_path.read_bytes())
    matches = [x for x in source_intake.get("fixtures", [])
               if str(x.get("source_fixture_id")) == fid]
    if len(matches) != 1:
        raise ValueError("ORIGINAL_PROVIDER_EVENT_NOT_UNIQUE")
    match = matches[0]
    if (str(match.get("source_competition_id")) != str(po["provider_competition_id"])
        or stamp(match["kickoff_utc"]) != stamp(po["kickoff_utc"])
        or str((final.get("homeTeam") or {}).get("id")) != str(match["home_source_team_id"])
        or str((final.get("awayTeam") or {}).get("id")) != str(match["away_source_team_id"])
        or str((final.get("competition") or {}).get("id")) != str(po["provider_competition_id"])):
        raise ValueError("FINAL_TEAM_COMPETITION_OR_START_IDENTITY_MISMATCH")
    original_p = result["research_probability_over25"]
    if type(original_p) not in (float, int) or not 0 < original_p < 1:
        raise ValueError("ORIGINAL_RESEARCH_P_INVALID")
    return {
        "settlement_path": rp.relative_to(root).as_posix(),
        "settlement_sha256": sha(rp),
        "provider_result_sha256": result["raw_result_sha256"],
        "outcome": int(result["over25_outcome"]),
        "original_research_p": original_p,
        "original_frozen_forecast_sha256": result["forecast_sha256"],
        "original_source_history_sha256": original["source_snapshot_sha256"],
        "identical_authenticated_history_capture": original["source_snapshot_sha256"] == po["history_raw_sha256"],
        "result_observed_at_utc": result["result_observed_at_utc"],
    }


def evaluate(root: Path, now=None):
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("EVALUATION_CLOCK_TIMEZONE_REQUIRED")
    now = now.astimezone(timezone.utc)
    grouped = defaultdict(list)
    paired, rejected, pending, unresolved, seen = [], [], [], [], set()
    for file in sorted((root / SOURCE).glob("20??-??-??/MATRIX_FREE_POISSON_V1_IMMUTABLE/*.json")):
        try:
            p, kickoff = safe_row(file, now)
            fid = str(p["fixture_id"])
            if fid in seen:
                raise ValueError("DUPLICATE_FREE_POISSON_FORECAST")
            seen.add(fid)
            if now <= kickoff:
                pending.append(fid)
                continue
            result = final_result(root, p, now)
            if result is None:
                unresolved.append(fid)
                continue
            y = result["outcome"]
            a = p["research_probability_over25"]
            b = result["original_research_p"]
            for value in (a, b):
                if not 0 < value < 1:
                    raise ValueError("INVALID_SCORING_INPUT")
            row = {
                "fixture_id": fid,
                "provider_competition_id": str(p["provider_competition_id"]),
                "poisson_forecast_sha256": sha(file),
                "poisson_frozen_at_utc": p["forecast_frozen_at_utc"],
                "poisson_source_history_sha256": p["history_raw_sha256"],
                **result,
                "poisson_p": a,
                "poisson_brier": (a - y)**2,
                "original_research_brier": (b - y)**2,
                "poisson_logloss": -(y * math.log(a) + (1-y) * math.log1p(-a)),
                "original_research_logloss": -(y * math.log(b) + (1-y) * math.log1p(-b)),
            }
            paired.append(row)
            grouped[row["provider_competition_id"]].append(row)
        except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            rejected.append({"path": file.relative_to(root).as_posix(),
                             "reason": str(exc)[:125]})
    groups = []
    for cid, rows in sorted(grouped.items()):
        n = len(rows)
        groups.append({
            "competition_id": cid,
            "independently_settled_pairs": n,
            "poisson_brier": round(sum(r["poisson_brier"] for r in rows)/n, 9),
            "original_research_brier": round(sum(r["original_research_brier"] for r in rows)/n, 9),
            "poisson_logloss": round(sum(r["poisson_logloss"] for r in rows)/n, 9),
            "original_research_logloss": round(sum(r["original_research_logloss"] for r in rows)/n, 9),
            "gate_30": n >= 30,
            "automatic_promotion": False,
        })
    n = len(paired)
    return {
        "schema": "MATRIX_FREE_POISSON_POSTMATCH_PROSPECTIVE_SCORECARD_V1",
        "generated_at_utc": now.isoformat(),
        "status": "READ_ONLY_PROSPECTIVE_COMPARISON_NO_PRODUCTION",
        "independent_model": P_MODEL,
        "independently_verified_settled_pairs": n,
        "future_forecasts_pending": len(pending),
        "started_without_verified_final": len(unresolved),
        "rejected_forecasts_or_settlements": rejected,
        "per_competition": groups,
        "mean_poisson_brier": round(sum(r["poisson_brier"] for r in paired)/n, 9) if n else None,
        "mean_original_research_brier": round(sum(r["original_research_brier"] for r in paired)/n, 9) if n else None,
        "mean_poisson_logloss": round(sum(r["poisson_logloss"] for r in paired)/n, 9) if n else None,
        "mean_original_research_logloss": round(sum(r["original_research_logloss"] for r in paired)/n, 9) if n else None,
        "pairs": paired,
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "canonical_model_parity_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--out",type=Path,default=OUT)
    args=p.parse_args()
    if set(args.out.parts) & {"notifications", "telegram", "tennis_signals", "daily_prematch_reports"}:
        raise SystemExit("INDEPENDENT_OOS_CANNOT_WRITE_SIGNALS")
    data=evaluate(args.root)
    dest=args.out if args.out.is_absolute() else args.root/args.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"settled":data["independently_verified_settled_pairs"],
                     "pending":data["future_forecasts_pending"],
                     "unresolved":data["started_without_verified_final"],
                     "rejected":len(data["rejected_forecasts_or_settlements"]),
                     "signals":False},sort_keys=True))

if __name__ == "__main__":
    main()
