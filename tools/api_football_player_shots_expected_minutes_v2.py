from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from math import exp, floor, log
from pathlib import Path
from typing import Any, Mapping

EPS = 1e-15
MIN_OVERALL_HISTORY = 5
MIN_ROLE_HISTORY = 3
MAX_OVERALL_HISTORY = 20
MAX_ROLE_HISTORY = 10
MIN_TRAIN = 200
MIN_VALIDATION = 50

DATASET_DIRS = (
    Path("evidence/api_football/market_expansion/historical_prior_season"),
    Path("evidence/api_football/market_expansion/historical_bootstrap"),
    Path("evidence/api_football/market_expansion/historical_warmup"),
    Path("evidence/api_football/market_expansion/historical_statsrich"),
    Path("evidence/api_football/market_expansion/historical_statsrich_3"),
)


def _utc(value: object) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _load_fixture_sources() -> tuple[list[dict[str, Any]], int]:
    by_id: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for root in DATASET_DIRS:
        dataset = root / "normalized_dataset.jsonl"
        if not dataset.exists():
            continue
        for raw in dataset.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            fid = str(row.get("fixture_id") or "").strip()
            kickoff = row.get("kickoff_utc")
            if not fid or not kickoff:
                continue
            if fid in by_id:
                duplicates += 1
                continue
            by_id[fid] = {
                "fixture_id": fid,
                "kickoff_utc": kickoff,
                "league_id": str(row.get("league_id") or ""),
                "season": row.get("season"),
                "raw_players_path": str(root / "raw" / f"fixture_{fid}_players.bin"),
            }
    rows = list(by_id.values())
    rows.sort(key=lambda r: (_utc(r["kickoff_utc"]), int(r["fixture_id"])))
    return rows, duplicates


def _appearances(path: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    out = []
    for team_row in payload.get("response") or []:
        if not isinstance(team_row, Mapping):
            continue
        team = team_row.get("team") if isinstance(team_row.get("team"), Mapping) else {}
        for player_row in team_row.get("players") or []:
            if not isinstance(player_row, Mapping):
                continue
            player = player_row.get("player") if isinstance(player_row.get("player"), Mapping) else {}
            pid = str(player.get("id") or "").strip()
            if not pid or pid == "0":
                continue
            stats = player_row.get("statistics") if isinstance(player_row.get("statistics"), list) else []
            for stat in stats:
                if not isinstance(stat, Mapping):
                    continue
                games = stat.get("games") if isinstance(stat.get("games"), Mapping) else {}
                shots = stat.get("shots") if isinstance(stat.get("shots"), Mapping) else {}
                minutes = games.get("minutes")
                substitute = games.get("substitute")
                shot_count = shots.get("total")
                if minutes is None or shot_count is None or not isinstance(substitute, bool):
                    continue
                try:
                    minutes_f = float(minutes)
                    shots_f = float(shot_count)
                except (TypeError, ValueError):
                    continue
                if minutes_f <= 0 or shots_f < 0:
                    continue
                out.append({
                    "player_id": pid,
                    "player_name": player.get("name"),
                    "team_id": str(team.get("id") or ""),
                    "team_name": team.get("name"),
                    "minutes": minutes_f,
                    "shots": shots_f,
                    "role": "SUBSTITUTE" if substitute else "STARTER",
                })
                break
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _aggregate_rate_per90(rows: list[dict[str, Any]]) -> float:
    minutes = sum(float(x["minutes"]) for x in rows)
    if minutes <= 0:
        raise ValueError("NONPOSITIVE_HISTORY_MINUTES")
    return 90.0 * sum(float(x["shots"]) for x in rows) / minutes


def build_dataset(out_dir: Path) -> dict[str, Any]:
    fixtures, duplicate_fixture_ids = _load_fixture_sources()
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rows = []
    skipped_missing_raw = 0
    insufficient_overall = 0
    insufficient_role = 0
    current_minutes_used = False

    for fixture in fixtures:
        raw_path = Path(fixture["raw_players_path"])
        apps = _appearances(raw_path)
        if not raw_path.exists():
            skipped_missing_raw += 1
        pending = []
        for app in apps:
            pid = app["player_id"]
            prior = history[pid][-MAX_OVERALL_HISTORY:]
            if len(prior) < MIN_OVERALL_HISTORY:
                insufficient_overall += 1
            else:
                role_prior = [x for x in prior if x["role"] == app["role"]][-MAX_ROLE_HISTORY:]
                if len(role_prior) < MIN_ROLE_HISTORY:
                    insufficient_role += 1
                else:
                    last5 = prior[-5:]
                    role_recent = role_prior[-3:]
                    rows.append({
                        "fixture_id": fixture["fixture_id"],
                        "kickoff_utc": fixture["kickoff_utc"],
                        "league_id": fixture["league_id"],
                        "season": fixture["season"],
                        "player_id": pid,
                        "player_name": app["player_name"],
                        "team_id": app["team_id"],
                        "team_name": app["team_name"],
                        "lineup_role_reconstructed": app["role"],
                        "historical_role_label_source": "fixtures/players.games.substitute",
                        "prospective_role_source_required": "/fixtures/lineups",
                        "prior_appearance_count": len(prior),
                        "prior_role_appearance_count": len(role_prior),
                        "prior_mean_count": _mean([float(x["shots"]) for x in prior]),
                        "last5_mean_count": _mean([float(x["shots"]) for x in last5]),
                        "prior_mean_minutes": _mean([float(x["minutes"]) for x in prior]),
                        "last5_mean_minutes": _mean([float(x["minutes"]) for x in last5]),
                        "role_prior_shots_per90": _aggregate_rate_per90(role_prior),
                        "role_recent3_shots_per90": _aggregate_rate_per90(role_recent),
                        "expected_minutes_pit": _mean([float(x["minutes"]) for x in role_prior]),
                        "expected_minutes_source": "MEAN_PRIOR_SAME_ROLE_MINUTES_ONLY",
                        "target_shots": float(app["shots"]),
                        "current_match_minutes_postsettlement_audit_only": float(app["minutes"]),
                        "current_match_minutes_used_as_feature": False,
                        "same_match_shots_used_in_features": False,
                    })
            pending.append(app)

        for app in pending:
            history[app["player_id"]].append({
                "fixture_id": fixture["fixture_id"],
                "kickoff_utc": fixture["kickoff_utc"],
                "role": app["role"],
                "minutes": float(app["minutes"]),
                "shots": float(app["shots"]),
            })

    rows.sort(key=lambda r: (_utc(r["kickoff_utc"]), int(r["fixture_id"]), int(r["player_id"])))
    n = len(rows)
    val_n = MIN_VALIDATION if n >= MIN_TRAIN + MIN_VALIDATION else 0
    split = n - val_n
    for i, row in enumerate(rows):
        row["split"] = "TRAIN" if i < split else "VALIDATION"

    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "player_shots_role_expected_minutes_pit.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8",
    )
    manifest = {
        "schema": "MATRIX_PLAYER_SHOTS_ROLE_EXPECTED_MINUTES_PIT_V2",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "fixture_count": len(fixtures),
        "duplicate_fixture_ids_quarantined": duplicate_fixture_ids,
        "skipped_missing_raw": skipped_missing_raw,
        "row_count": n,
        "train_count": split,
        "validation_count": val_n,
        "minimum_overall_history": MIN_OVERALL_HISTORY,
        "minimum_same_role_history": MIN_ROLE_HISTORY,
        "insufficient_overall_history_count": insufficient_overall,
        "insufficient_same_role_history_count": insufficient_role,
        "feature_policy": "STRICTLY_PRIOR_APPEARANCES_AND_PRIOR_SAME_ROLE_MINUTES_ONLY",
        "historical_role_label_source": "fixtures/players.games.substitute",
        "prospective_role_source_required": "/fixtures/lineups",
        "cross_source_role_equivalence_certified": False,
        "current_match_minutes_used_as_feature": current_minutes_used,
        "same_match_target_used_in_features": False,
        "protected_final_holdout_used": False,
        "prospective_calibration_used": False,
        "odds_used_to_generate_probability": False,
        "dataset_path": str(dataset_path),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS" if val_n == MIN_VALIDATION else "INSUFFICIENT_ROLE_AWARE_SAMPLE",
    }
    (out_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1 - EPS)


def _poisson_over(mu: float, line: float) -> float:
    mu = max(0.01, float(mu))
    cut = int(floor(line))
    term = exp(-mu)
    cdf = term
    for k in range(1, cut + 1):
        term *= mu / k
        cdf += term
    return _clip(1 - cdf)


def _metrics(ys: list[int], ps: list[float]) -> dict[str, float]:
    if not ys or len(ys) != len(ps):
        raise ValueError("INVALID_METRIC_INPUT")
    brier = ll = 0.0
    buckets = [[] for _ in range(5)]
    for y, p0 in zip(ys, ps):
        p = _clip(p0)
        brier += (p - y) ** 2
        ll += -(y * log(p) + (1 - y) * log(1 - p))
        buckets[min(4, int(p * 5))].append((y, p))
    n = len(ys)
    ece = 0.0
    max_err = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        obs = sum(y for y, _ in bucket) / len(bucket)
        pred = sum(p for _, p in bucket) / len(bucket)
        err = abs(obs - pred)
        ece += len(bucket) / n * err
        max_err = max(max_err, err)
    return {
        "sample_size": n,
        "brier_score": brier / n,
        "log_loss": ll / n,
        "ece_5bin": ece,
        "max_calibration_error_5bin": max_err,
    }


def _v1_mu(row: Mapping[str, Any], alpha: float, beta: float) -> float:
    long = max(0.0, float(row["prior_mean_count"]))
    recent = max(0.0, float(row["last5_mean_count"]))
    prior_minutes = max(1.0, float(row["prior_mean_minutes"]))
    recent_minutes = max(1.0, float(row["last5_mean_minutes"]))
    count = (1 - alpha) * long + alpha * recent
    minute_ratio = min(1.5, max(0.5, recent_minutes / prior_minutes))
    return max(0.01, count * (minute_ratio ** beta))


def _v2_mu(row: Mapping[str, Any], alpha_recent_rate: float) -> float:
    long_rate = max(0.0, float(row["role_prior_shots_per90"]))
    recent_rate = max(0.0, float(row["role_recent3_shots_per90"]))
    rate = (1 - alpha_recent_rate) * long_rate + alpha_recent_rate * recent_rate
    expected_minutes = max(1.0, min(90.0, float(row["expected_minutes_pit"])))
    return max(0.01, rate * expected_minutes / 90.0)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def build_model(out_dir: Path) -> dict[str, Any]:
    dataset_path = out_dir / "player_shots_role_expected_minutes_pit.jsonl"
    rows = _load_jsonl(dataset_path)
    train = [x for x in rows if x.get("split") == "TRAIN"]
    validation = [x for x in rows if x.get("split") == "VALIDATION"]
    v1 = json.loads(Path(
        "evidence/api_football/market_expansion/player_models/player_shots_model.json"
    ).read_text(encoding="utf-8"))
    line = float(v1["evaluation_line"])
    v1_params = v1["model_parameters"]
    base = {
        "schema": "MATRIX_PLAYER_SHOTS_ROLE_EXPECTED_MINUTES_MODEL_V2",
        "lane": "PLAYER_SHOTS",
        "candidate": "role_aware_expected_minutes_v2",
        "source_dataset": str(dataset_path),
        "source_dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "train_count": len(train),
        "validation_count": len(validation),
        "evaluation_line": line,
        "comparison_champion": "player_shots_model_v1_same_rows",
        "validation_used_for_parameter_tuning": False,
        "protected_final_holdout_used": False,
        "prospective_calibration_used": False,
        "odds_used_to_generate_probability": False,
        "current_match_minutes_used_as_feature": False,
        "cross_source_role_equivalence_certified": False,
        "prematch_lineup_source_certified": False,
        "expected_minutes_pit_prospective_certified": False,
        "prospective_freeze_allowed": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    if len(train) < MIN_TRAIN or len(validation) < MIN_VALIDATION:
        return {**base, "status": "REJECTED_INSUFFICIENT_ROLE_AWARE_OOS", "metrics_opened": False}

    cut = max(150, int(len(train) * 0.80))
    cut = min(cut, len(train) - 25)
    inner_val = train[cut:]
    trials = []
    for alpha in (0.0, 0.25, 0.50, 0.75, 1.0):
        ys = [int(float(r["target_shots"]) > line) for r in inner_val]
        ps = [_poisson_over(_v2_mu(r, alpha), line) for r in inner_val]
        trials.append({"alpha_recent_rate": alpha, "internal_validation": _metrics(ys, ps)})
    trials.sort(key=lambda x: (x["internal_validation"]["log_loss"], x["internal_validation"]["brier_score"]))
    selected = trials[0]

    ys = [int(float(r["target_shots"]) > line) for r in validation]
    v1_ps = [
        _poisson_over(
            _v1_mu(r, float(v1_params["alpha_recent"]), float(v1_params["beta_prior_minutes_ratio"])),
            line,
        )
        for r in validation
    ]
    v2_ps = [_poisson_over(_v2_mu(r, float(selected["alpha_recent_rate"])), line) for r in validation]
    m1 = _metrics(ys, v1_ps)
    m2 = _metrics(ys, v2_ps)
    delta_brier = m2["brier_score"] - m1["brier_score"]
    delta_logloss = m2["log_loss"] - m1["log_loss"]
    passed = (
        delta_brier < 0
        and delta_logloss < 0
        and m2["ece_5bin"] <= 0.10
        and m2["max_calibration_error_5bin"] <= 0.20
    )
    params = {
        "alpha_recent_rate": selected["alpha_recent_rate"],
        "expected_minutes_method": "MEAN_PRIOR_SAME_ROLE_MINUTES_ONLY",
        "minimum_same_role_history": MIN_ROLE_HISTORY,
        "evaluation_line": line,
    }
    result = {
        **base,
        "status": "HISTORICAL_OOS_PASS_ROLE_AWARE_PROSPECTIVE_BLOCKED"
        if passed else "REJECTED_HISTORICAL_OOS_ROLE_AWARE_V2",
        "metrics_opened": True,
        "selected_parameters": params,
        "selected_parameters_sha256": hashlib.sha256(
            json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "internal_selection": {
            "selection_rows": len(inner_val),
            "trial_count": len(trials),
            "selected": selected,
            "final_validation_used_for_selection": False,
        },
        "validation": {
            "champion_v1_same_rows": m1,
            "challenger_v2": m2,
            "delta_brier_v2_minus_v1": delta_brier,
            "delta_log_loss_v2_minus_v1": delta_logloss,
            "gate_passed": passed,
        },
        "expected_minutes_algorithm_historical_oos_validated": passed,
        "prospective_blocker": (
            "PREMATCH_LINEUP_ROLE_SOURCE_NOT_CERTIFIED_AND_EXPECTED_MINUTES_PROSPECTIVE_GATE_CLOSED"
        ),
    }
    return result


def main() -> None:
    out_dir = Path(
        "evidence/api_football/market_expansion/player_shots_expected_minutes_v2"
    )
    dataset = build_dataset(out_dir)
    model = build_model(out_dir)
    model_path = out_dir / "model.json"
    model_path.write_text(
        json.dumps(model, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "schema": "MATRIX_PLAYER_SHOTS_EXPECTED_MINUTES_V2_SUMMARY",
        "dataset_status": dataset["status"],
        "dataset_rows": dataset["row_count"],
        "train_rows": dataset["train_count"],
        "validation_rows": dataset["validation_count"],
        "model_status": model["status"],
        "historical_oos_gate_passed": bool(model.get("validation", {}).get("gate_passed")),
        "cross_source_role_equivalence_certified": False,
        "prematch_lineup_source_certified": False,
        "expected_minutes_pit_prospective_certified": False,
        "prospective_freeze_allowed": False,
        "real_money": "BLOCKED",
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
