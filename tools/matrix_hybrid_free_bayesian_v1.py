"""Research-only Bayesian candidate for MATRIX Híbrida Élite, fully source-bound.

Uses the historical results already observed in authenticated, SHA-preserved
football-data.org raw source bytes, through the existing frozen Poisson receipt
and separate research-only pair bridge. It does not consume original p_MATRIX,
postmatch outcomes for its target, odds or later observations. No promotion.

Mathematics mirrors the existing isolated hierarchical beta-binomial research
challenger's prior and pooling constants, but is an INDEPENDENT FREE-SOURCE
RESEARCH CONTRACT, not the certified original hybrid laboratory admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from tools.matrix_hybrid_elite_bayesian_shadow import (
    MIN_POOLED_OBS, PRIOR_WEIGHT,
)
from tools.matrix_hybrid_elite_research_pair_bridge import check_one, source_envelope
from tools.matrix_independent_free_poisson_oos import stamp
from tools.matrix_independent_free_poisson_v1 import decode_group

SCHEMA = "MATRIX_HYBRID_FREE_BAYESIAN_OVER25_RESEARCH_V1"
REPORT = "MATRIX_HYBRID_FREE_BAYESIAN_RESEARCH_CYCLE_V1"
MODEL = "MATRIX_HYBRID_FREE_BAYESIAN_OVER25_V1"
MIN_LEAGUE_HISTORY = 20


def require(test: bool, reason: str):
    if not test:
        raise ValueError(reason)


def read_bound(root: Path, rel: str, digest: str) -> dict:
    p = Path(rel)
    require(not p.is_absolute() and ".." not in p.parts, "UNSAFE_HISTORY_RECEIPT_PATH")
    content = (root / p).read_bytes()
    require(hashlib.sha256(content).hexdigest() == digest, "HYBRID_SOURCE_RECEIPT_SHA_MISMATCH")
    return json.loads(content)


def validate_pairs_manifest(doc: dict):
    require(doc.get("schema") == "MATRIX_HYBRID_ELITE_RESEARCH_PRELABEL_PAIRS_V1" and
            doc.get("real_money") == "BLOCKED" and
            doc.get("telegram_signal_authorized") is False and
            doc.get("production_p_matrix_authorized") is False and
            doc.get("automatic_model_promotion") is False and
            doc.get("formal_hybrid_elite_lab_rows_admitted") == 0,
            doc.get("existing_official_original_p_matrix_pairs") == 0,
            "HYBRID_RESEARCH_PAIR_MANIFEST_UNTRUSTED")
    pairs = doc.get("prelabel_research_pairs")
    require(isinstance(pairs, list), "HYBRID_PAIRS_NOT_ARRAY")
    require(len(pairs) == doc.get("recovered_research_pair_count"),
            "HYBRID_PAIR_COUNT_MISMATCH")
    require(doc.get("rejected_research_pair_count") == 0,
            "HYBRID_PAIR_SOURCE_INTEGRITY_REJECTED")
    return pairs


def score_one(root: Path, entry: dict, now: datetime, memo: dict, raw_groups: dict):
    # Recheck the exact immutable physical source from the original bridge,
    # not only the claimed summary input. Never use target final scores.
    po_path = Path(entry["poisson_freeze_path"])
    po_source = read_bound(root, po_path.as_posix(), entry["poisson_freeze_sha256"])
    physical = check_one(root, root / po_path, now, memo)
    require(physical == entry, "HYBRID_PAIR_RECEIPT_DOES_NOT_MATCH_PHYSICAL_BYTES")
    kickoff = stamp(entry["event_start_at_utc"])
    require(now < kickoff, "HYBRID_BAYESIAN_FORECAST_AFTER_KICKOFF")
    require(stamp(po_source["forecast_frozen_at_utc"]) <= now, "HYBRID_POISSON_FROZEN_IN_FUTURE")
    original = read_bound(root, entry["original_freeze_path"], entry["original_freeze_sha256"])
    shadow, intake = source_envelope(root, original, memo)
    require(original["source_snapshot_sha256"] == entry["common_history_raw_sha256"],
            "HYBRID_BAYESIAN_ORIGINAL_HISTORY_SHA_NOT_EQUAL")
    # The history capture was already frozen before *both* research predictions.
    source_key = original["source_shadow_file_sha256"]
    if source_key not in raw_groups:
        decoded = {}
        for cid, group in shadow["authenticated_raw_group_replay_evidence"].items():
            observed, rows, ignored = decode_group(group, cid, now)
            require(observed < kickoff, "HYBRID_RAW_SOURCE_AFTER_EVENT")
            decoded[str(cid)] = {
                "observed_at": observed,
                "source_sha256": group["source_payload_sha256"],
                "rows": rows,
                "rows_without_provider_lastupdate": ignored,
            }
        raw_groups[source_key] = decoded
    decoded = raw_groups[source_key]
    target_league = str(po_source["provider_competition_id"])
    require(target_league in decoded, "HYBRID_TARGET_LEAGUE_NOT_AUTHENTICATED")
    pooled = []
    league = []
    raw_hashes = {}
    for cid, group in sorted(decoded.items()):
        require(group["observed_at"] <= now, "HYBRID_GROUP_OBSERVED_AFTER_FREEZE")
        eligible = [row for row in group["rows"]
                    if row["kickoff_utc"] < group["observed_at"]
                    and row["kickoff_utc"] < now
                    and row["kickoff_utc"] < kickoff]
        raw_hashes[cid] = group["source_sha256"]
        pooled.extend((cid, r) for r in eligible)
        if cid == target_league:
            league = eligible
    require(len({(cid,r["fixture_id"]) for cid,r in pooled}) == len(pooled),
            "HYBRID_DUPLICATE_HISTORICAL_GAME")
    require(len(pooled) >= MIN_POOLED_OBS, "HYBRID_POOLED_HISTORY_BELOW_MINIMUM")
    require(len(league) >= MIN_LEAGUE_HISTORY, "HYBRID_TARGET_LEAGUE_HISTORY_BELOW_MINIMUM")
    pool_over = sum(int(r["home_goals"] + r["away_goals"] > 2) for _, r in pooled)
    league_over = sum(int(r["home_goals"] + r["away_goals"] > 2) for r in league)
    pool_prior = (2 + pool_over) / (4 + len(pooled))
    p = (PRIOR_WEIGHT * pool_prior + league_over) / (PRIOR_WEIGHT + len(league))
    require(0 < p < 1 and math.isfinite(p), "HYBRID_BAYESIAN_INVALID_RESEARCH_P")
    return {
        "schema": SCHEMA,
        "model_id": MODEL,
        "lane": "FOOTBALL_OVER25",
        "physical_event_id": entry["physical_event_id"],
        "provider": "FOOTBALL_DATA_ORG",
        "provider_competition_id": target_league,
        "event_start_at_utc": kickoff.isoformat(),
        "forecast_frozen_at_utc": now.isoformat(),
        "source_original_research_freeze_sha256": entry["original_freeze_sha256"],
        "source_independent_poisson_freeze_sha256": entry["poisson_freeze_sha256"],
        "source_history_response_sha256_by_competition": raw_hashes,
        "same_authenticated_target_history_sha256": entry["common_history_raw_sha256"],
        "certified_before_prediction_historical_pool_count": len(pooled),
        "certified_before_prediction_league_count": len(league),
        "prior_poisson_train_score_not_used": True,
        "poisson_prediction_not_used_as_bayesian_feature": True,
        "target_outcome_not_used": True,
        "pooled_beta_prior_strength": [2, 2],
        "pooled_certified_over25_success_count": pool_over,
        "league_certified_over25_success_count": league_over,
        "group_prior_weight": PRIOR_WEIGHT,
        "p_bayesian_research_over25": round(p, 12),
        "original_official_p_matrix_parity_certified": False,
        "independent_hybrid_future_oos_certified": False,
        "model_promotion_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def build(root: Path, manifest: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    require(now.utcoffset() is not None, "BAYESIAN_CLOCK_REQUIRES_TZ")
    now = now.astimezone(timezone.utc)
    pairs = validate_pairs_manifest(manifest)
    memo, raw_groups = {}, {}
    scored, rejected, seen = [], [], set()
    for p in pairs:
        try:
            key = str(p["physical_event_id"])
            require(key not in seen, "DUPLICATE_HYBRID_EVENT_ID")
            seen.add(key)
            scored.append(score_one(root, p, now, memo, raw_groups))
        except (ValueError, TypeError, KeyError, OSError,
                json.JSONDecodeError) as err:
            rejected.append({"physical_event_id": p.get("physical_event_id"),
                             "reason": str(err)[:160]})
    return {
        "schema": REPORT,
        "model_id": MODEL,
        "generated_at_utc": now.isoformat(),
        "source_order": ["SOFASCORE", "FLASHSCORE", "FOOTBALL_DATA_ORG"],
        "scored_count": len(scored),
        "blocked_count": len(rejected),
        "scored": scored,
        "blocked": rejected,
        "formal_original_matrix_p_comparison_allowed": False,
        "original_calibrated_parameters_modified": False,
        "independent_model_research_only": True,
        "automatic_model_promotion": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--pairs", type=Path, default=Path(
        "evidence/matrix_hybrid_elite/MATRIX_HYBRID_RESEARCH_PRELABEL_PAIRS_LAST.json"))
    p.add_argument("--out", type=Path, default=Path(
        "evidence/matrix_hybrid_elite/MATRIX_HYBRID_FREE_BAYESIAN_LAST.json"))
    a = p.parse_args()
    require(not ({"telegram", "notifications", "tennis_signals", "daily_prematch_reports"} & set(a.out.parts)),
            "BAYESIAN_SHADOW_CANNOT_WRITE_PRODUCTION")
    manifest = json.loads((a.root / a.pairs).read_bytes())
    report = build(a.root, manifest)
    base = a.root / "evidence/football_world_inventory" / "2026-11-21" / "MATRIX_HYBRID_FREE_BAYESIAN_V1_IMMUTABLE"
    base.mkdir(parents=True, exist_ok=True)
    stored = 0
    for row in report["scored"]:
        dest = base / (row["physical_event_id"] + ".json")
        if dest.is_file():
            prior = json.loads(dest.read_bytes())
            require(prior.get("schema") == SCHEMA and
                    prior.get("model_id") == MODEL and
                    prior.get("physical_event_id") == row["physical_event_id"] and
                    prior.get("same_authenticated_target_history_sha256") ==
                    row["same_authenticated_target_history_sha256"] and
                    prior.get("real_money") == "BLOCKED" and
                    prior.get("telegram_signal_authorized") is False,
                    "BAYESIAN_FROZEN_FORECAST_CANNOT_BE_REWRITTEN")
        else:
            with dest.open("x", encoding="utf-8") as fh:
                json.dump(row, fh, ensure_ascii=False, sort_keys=True)
                fh.write("\n")
            stored += 1
    report["immutable_new_forecasts"] = stored
    report["immutable_already_existing"] = len(report["scored"]) - stored
    dest = a.root / a.out
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"bayesian_research_forecasts": report["scored_count"],
                      "new": stored,"blocked": report["blocked_count"],
                      "signals": False,"real_money":"BLOCKED"}, sort_keys=True))


if __name__ == "__main__":
    main()
