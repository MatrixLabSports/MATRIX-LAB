from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SOURCE = Path("evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv")
SOURCE_MANIFEST = Path("evidence/cor0203/preholdout/MANIFEST.json")
LANE_ID = "ATP_CHALLENGER_MEN_SINGLES_CLAY"
TRAIN_END = 20260630
VALIDATION_END = 20260731
HISTORICAL_OOS_END = 20260914


def _float_or_none(value: object) -> float | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        return float(token)
    except ValueError:
        return None


def _int_or_none(value: object) -> int | None:
    token = str(value or "").strip()
    if not token:
        return None
    try:
        return int(float(token))
    except ValueError:
        return None


def _excluded_score(score: object) -> str | None:
    token = str(score or "").strip().upper()
    if "RET" in token:
        return "RETIREMENT"
    if "W/O" in token or token == "WO" or "WALKOVER" in token:
        return "WALKOVER"
    return None


def _physical_key(row: dict[str, str]) -> str:
    ids = sorted([row["winner_id"], row["loser_id"]])
    raw = "|".join([
        row["tourney_id"],
        row["tourney_date"],
        row["match_num"],
        *ids,
    ]).encode()
    return hashlib.sha256(raw).hexdigest()


def _canonicalize(row: dict[str, str]) -> dict[str, Any]:
    winner_id = row["winner_id"]
    loser_id = row["loser_id"]
    a_is_winner = winner_id <= loser_id
    if a_is_winner:
        a_prefix, b_prefix = "winner", "loser"
    else:
        a_prefix, b_prefix = "loser", "winner"

    def value(prefix: str, field: str) -> str:
        return row[f"{prefix}_{field}"]

    return {
        "physical_event_key": _physical_key(row),
        "tourney_id": row["tourney_id"],
        "tourney_name": row["tourney_name"],
        "tourney_date": int(row["tourney_date"]),
        "surface": row["surface"],
        "indoor": row["indoor"],
        "round": row["round"],
        "match_num": int(row["match_num"]),
        "player_a_id": value(a_prefix, "id"),
        "player_a_name": value(a_prefix, "name"),
        "player_a_hand": value(a_prefix, "hand") or None,
        "player_a_age": _float_or_none(value(a_prefix, "age")),
        "player_a_rank": _int_or_none(value(a_prefix, "rank")),
        "player_a_rank_points": _int_or_none(value(a_prefix, "rank_points")),
        "player_b_id": value(b_prefix, "id"),
        "player_b_name": value(b_prefix, "name"),
        "player_b_hand": value(b_prefix, "hand") or None,
        "player_b_age": _float_or_none(value(b_prefix, "age")),
        "player_b_rank": _int_or_none(value(b_prefix, "rank")),
        "player_b_rank_points": _int_or_none(value(b_prefix, "rank_points")),
        "label_a_win": 1 if a_is_winner else 0,
        "score": row["score"],
        "best_of": int(row["best_of"]),
    }


def build_dataset(source: Path = SOURCE) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    raw_clay = []
    excluded = defaultdict(int)
    with source.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row.get("tourney_level") != "C":
                continue
            if row.get("surface") != "Clay":
                continue
            raw_clay.append(row)

    keys = [_physical_key(row) for row in raw_clay]
    duplicate_groups = len(keys) - len(set(keys))
    if duplicate_groups:
        raise ValueError(f"CLAY_SOURCE_DUPLICATE_PHYSICAL_KEYS:{duplicate_groups}")

    clean = []
    for row in raw_clay:
        reason = _excluded_score(row.get("score"))
        if reason:
            excluded[reason] += 1
            continue
        clean.append(_canonicalize(row))

    clean.sort(key=lambda r: (
        r["tourney_date"],
        r["tourney_id"],
        r["match_num"],
        r["physical_event_key"],
    ))

    for row in clean:
        date = row["tourney_date"]
        if date <= TRAIN_END:
            row["development_split"] = "TRAIN"
        elif date <= VALIDATION_END:
            row["development_split"] = "VALIDATION"
        elif date <= HISTORICAL_OOS_END:
            row["development_split"] = "FINAL_HISTORICAL_OOS"
        else:
            raise ValueError(f"CLAY_ROW_AFTER_SEALED_SOURCE_MAX:{date}")

    split_counts = defaultdict(int)
    missing = defaultdict(int)
    tournaments = set()
    players = set()
    for row in clean:
        split_counts[row["development_split"]] += 1
        tournaments.add((row["tourney_id"], row["tourney_name"]))
        players.update([row["player_a_id"], row["player_b_id"]])
        for field in (
            "player_a_age", "player_b_age",
            "player_a_rank", "player_b_rank",
            "player_a_rank_points", "player_b_rank_points",
        ):
            if row[field] is None:
                missing[field] += 1

    audit = {
        "raw_clay_rows": len(raw_clay),
        "clean_completed_rows": len(clean),
        "excluded": dict(sorted(excluded.items())),
        "duplicate_physical_key_groups": 0,
        "unique_tournaments": len(tournaments),
        "unique_players": len(players),
        "min_tourney_date": min(r["tourney_date"] for r in clean),
        "max_tourney_date": max(r["tourney_date"] for r in clean),
        "split_counts": dict(split_counts),
        "missing_counts": dict(missing),
    }
    return clean, audit


@dataclass
class Metrics:
    n: int
    brier: float
    log_loss: float
    accuracy: float


def _metrics(predictions: list[tuple[float, int]]) -> Metrics:
    if not predictions:
        raise ValueError("NO_PREDICTIONS")
    eps = 1e-15
    brier = sum((p-y)**2 for p,y in predictions) / len(predictions)
    log_loss = -sum(
        y*math.log(max(eps, min(1-eps, p))) +
        (1-y)*math.log(max(eps, min(1-eps, 1-p)))
        for p,y in predictions
    ) / len(predictions)
    accuracy = sum((p >= 0.5) == bool(y) for p,y in predictions) / len(predictions)
    return Metrics(len(predictions), brier, log_loss, accuracy)


def _elo_probability(ra: float, rb: float, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rb-ra)/scale))


def evaluate_elo(
    rows: Iterable[dict[str, Any]],
    *,
    k: float,
    score_split: str | None = None,
) -> tuple[Metrics | None, dict[str, float]]:
    ratings: dict[str, float] = defaultdict(lambda: 1500.0)
    scored: list[tuple[float,int]] = []

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["tourney_date"]].append(row)

    for date in sorted(grouped):
        pending = []
        for row in grouped[date]:
            ra = ratings[row["player_a_id"]]
            rb = ratings[row["player_b_id"]]
            p = _elo_probability(ra, rb)
            y = int(row["label_a_win"])
            if score_split is not None and row["development_split"] == score_split:
                scored.append((p,y))
            pending.append((row, p, y, ra, rb))
        # Same-day batch update: no unknown intraday order is used.
        deltas: dict[str, float] = defaultdict(float)
        for row,p,y,ra,rb in pending:
            delta = k * (y-p)
            deltas[row["player_a_id"]] += delta
            deltas[row["player_b_id"]] -= delta
        for player,delta in deltas.items():
            ratings[player] += delta

    return (_metrics(scored) if scored else None), dict(ratings)


def select_and_evaluate_elo(rows: list[dict[str, Any]]) -> dict[str, Any]:
    development_rows = [
        r for r in rows
        if r["development_split"] in {"TRAIN","VALIDATION"}
    ]
    validation_rows = [r for r in rows if r["development_split"] == "VALIDATION"]
    final_rows = [r for r in rows if r["development_split"] == "FINAL_HISTORICAL_OOS"]

    candidates = []
    for k in (16.0, 24.0, 32.0, 40.0):
        metrics,_ = evaluate_elo(development_rows, k=k, score_split="VALIDATION")
        assert metrics is not None
        candidates.append({
            "k": k,
            "validation": metrics.__dict__,
        })
    chosen = min(
        candidates,
        key=lambda x: (x["validation"]["brier"], x["validation"]["log_loss"], x["k"]),
    )
    chosen_k = float(chosen["k"])

    # Final historical OOS is opened exactly once after K selection.
    full_rows = development_rows + final_rows
    final_metrics,_ = evaluate_elo(
        full_rows,
        k=chosen_k,
        score_split="FINAL_HISTORICAL_OOS",
    )
    assert final_metrics is not None

    baseline = _metrics([(0.5, int(r["label_a_win"])) for r in final_rows])
    brier_improvement = baseline.brier - final_metrics.brier
    logloss_improvement = baseline.log_loss - final_metrics.log_loss
    status = (
        "PASS_HISTORICAL_OOS_CANDIDATE_NOT_PROMOTED"
        if brier_improvement > 0 and logloss_improvement > 0
        else "FAIL_HISTORICAL_OOS_NO_PROMOTION"
    )
    return {
        "schema": "MATRIX_TENNIS_CLAY_ELO_CANDIDATE_V1",
        "lane_id": LANE_ID,
        "candidate_identity": "ATP_CHALLENGER_CLAY_ELO_V1",
        "orientation": "PLAYER_A_IS_LEXICOGRAPHICALLY_SMALLER_PLAYER_ID",
        "rating_initial": 1500.0,
        "probability_scale": 400.0,
        "same_day_update_policy": "BATCH_AFTER_ALL_MATCHES_ON_TOURNEY_DATE",
        "parameter_selection": {
            "selection_split": "VALIDATION",
            "k_grid": [16.0,24.0,32.0,40.0],
            "candidates": candidates,
            "chosen_k": chosen_k,
            "final_historical_oos_not_used_for_selection": True,
        },
        "final_historical_oos": final_metrics.__dict__,
        "baseline_0_5": baseline.__dict__,
        "brier_improvement_vs_0_5": brier_improvement,
        "log_loss_improvement_vs_0_5": logloss_improvement,
        "status": status,
        "prospective_holdout_created": False,
        "prospective_observations": 0,
        "automatic_promotion": False,
        "real_money": "BLOCKED",
    }


def write_outputs(out_root: Path) -> dict[str, Any]:
    rows,audit = build_dataset()
    source_manifest = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    source_sha = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    if source_sha != source_manifest["member_sha256"]:
        raise ValueError("CLAY_SOURCE_SHA_MISMATCH")

    out_root.mkdir(parents=True, exist_ok=True)
    dataset_path = out_root / "historical_pit_dataset.csv"
    fieldnames = list(rows[0].keys())
    with dataset_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    elo = select_and_evaluate_elo(rows)
    elo_path = out_root / "elo_candidate_v1.json"
    elo_path.write_text(json.dumps(elo, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest = {
        "schema": "MATRIX_TENNIS_ATP_CHALLENGER_CLAY_BOOTSTRAP_V1",
        "lane_id": LANE_ID,
        "status": "HISTORICAL_PIT_BUILT_AND_ELO_OOS_EVALUATED",
        "source": {
            "path": str(SOURCE),
            "schema": source_manifest["schema"],
            "source_archive": source_manifest["source_archive"],
            "source_member_sha256": source_manifest["member_sha256"],
            "verified_source_sha256": source_sha,
            "source_max_tourney_date": source_manifest["max_tourney_date"],
            "pit_rule": source_manifest["pit_rule"],
        },
        "domain": {
            "circuit": "ATP_CHALLENGER",
            "gender": "MEN",
            "format": "SINGLES",
            "surface": "CLAY",
            "market": "MATCH_WINNER",
        },
        "audit": audit,
        "splits": {
            "TRAIN": {"end": str(TRAIN_END), "count": audit["split_counts"]["TRAIN"]},
            "VALIDATION": {"start": "20260701", "end": str(VALIDATION_END), "count": audit["split_counts"]["VALIDATION"]},
            "FINAL_HISTORICAL_OOS": {"start": "20260801", "end": str(HISTORICAL_OOS_END), "count": audit["split_counts"]["FINAL_HISTORICAL_OOS"]},
        },
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "elo_candidate_sha256": hashlib.sha256(elo_path.read_bytes()).hexdigest(),
        "prospective_holdout_status": "NOT_CREATED",
        "prospective_observations": 0,
        "metrics_opened": False,
        "cor0203_reused": False,
        "cor0203_modified": False,
        "automatic_model_promotion": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    manifest_path = out_root / "bootstrap_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-root",
        default="evidence/tennis_parallel_lanes/ATP_CHALLENGER_MEN_SINGLES_CLAY/bootstrap",
    )
    args = parser.parse_args()
    result = write_outputs(Path(args.out_root))
    print(json.dumps({
        "status": result["status"],
        "raw_clay_rows": result["audit"]["raw_clay_rows"],
        "clean_completed_rows": result["audit"]["clean_completed_rows"],
        "split_counts": result["audit"]["split_counts"],
        "dataset_sha256": result["dataset_sha256"],
        "elo_candidate_sha256": result["elo_candidate_sha256"],
        "prospective_holdout_status": result["prospective_holdout_status"],
        "cor0203_modified": result["cor0203_modified"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
