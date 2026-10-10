from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, factorial, log
from pathlib import Path
from typing import Any, Mapping

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle

FINAL_STATUSES = {"FT", "AET", "PEN"}
MIN_TEAM_HISTORY = 5
MAX_TEAM_HISTORY = 20
MIN_GROUP_BASELINE_HISTORY = 20
SCORE_CAP = 10
EPS = 1e-12
MODEL = "calibrated_log_pool_v1"
PARAMS_1X2 = {"a": 1.0, "c": 0.8}
PARAMS_OVER25 = {"a": 0.6, "b": 0.0, "c": 0.4}


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _canonical_hash(payload: Any) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _clip(p: float) -> float:
    return min(max(float(p), EPS), 1.0 - EPS)


def _logit(p: float) -> float:
    p = _clip(p)
    return log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = exp(-x)
        return 1.0 / (1.0 + z)
    z = exp(x)
    return z / (1.0 + z)


def _poisson(k: int, lam: float) -> float:
    return exp(-lam) * (lam ** k) / factorial(k)


def _mean(values: list[int]) -> float:
    if not values:
        raise ValueError("MEAN_REQUIRES_VALUES")
    return sum(values) / len(values)


def _score_probs(home_lambda: float, away_lambda: float) -> dict[str, Any]:
    h = d = a = o25 = mass = 0.0
    for hg in range(SCORE_CAP + 1):
        hp = _poisson(hg, home_lambda)
        for ag in range(SCORE_CAP + 1):
            p = hp * _poisson(ag, away_lambda)
            mass += p
            if hg > ag:
                h += p
            elif hg == ag:
                d += p
            else:
                a += p
            if hg + ag >= 3:
                o25 += p
    if mass <= 0:
        raise ValueError("INVALID_POISSON_MASS")
    return {"1x2": {"H": h/mass, "D": d/mass, "A": a/mass}, "over_2_5": o25/mass}


def _fixture(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    fixture, teams, goals = raw.get("fixture"), raw.get("teams"), raw.get("goals")
    if not all(isinstance(x, Mapping) for x in (fixture, teams, goals)):
        return None
    status, home, away = fixture.get("status"), teams.get("home"), teams.get("away")
    if not all(isinstance(x, Mapping) for x in (status, home, away)):
        return None
    if str(status.get("short") or "").upper().strip() not in FINAL_STATUSES:
        return None
    hg, ag = goals.get("home"), goals.get("away")
    try:
        fid, hid, aid = str(int(fixture.get("id"))), str(int(home.get("id"))), str(int(away.get("id")))
        kickoff = _utc(fixture.get("date"))
    except (TypeError, ValueError):
        return None
    if isinstance(hg, bool) or isinstance(ag, bool) or not isinstance(hg, int) or not isinstance(ag, int) or hg < 0 or ag < 0:
        return None
    return {"fixture_id": fid, "kickoff_utc": kickoff, "home_team_id": hid, "away_team_id": aid, "home_goals": hg, "away_goals": ag}


def _load_group(path: Path) -> tuple[list[dict[str, Any]], str]:
    raw = path.read_bytes()
    payload = json.loads(raw.decode("utf-8"))
    response = payload.get("response") if isinstance(payload, Mapping) else None
    if not isinstance(response, list):
        raise ValueError("RAW_GROUP_RESPONSE_INVALID")
    rows = [f for item in response for f in [_fixture(item)] if f is not None]
    rows.sort(key=lambda r: (r["kickoff_utc"], int(r["fixture_id"])))
    return rows, sha256(raw).hexdigest()


def _team_view(row: Mapping[str, Any], team_id: str) -> tuple[int, int]:
    if row["home_team_id"] == team_id:
        return int(row["home_goals"]), int(row["away_goals"])
    if row["away_team_id"] == team_id:
        return int(row["away_goals"]), int(row["home_goals"])
    raise ValueError("TEAM_NOT_IN_FIXTURE")


def _canonical_team_history(target: Mapping[str, Any], side: str, kickoff: datetime) -> list[tuple[int, int]]:
    key = f"{side}_history"
    team_key = f"{side}_team_id"
    rows = target.get(key)
    if not isinstance(rows, list):
        return []
    expected_team_id = str(target.get(team_key) or "")
    output: list[tuple[int, int]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            raise ValueError(f"CANONICAL_{side.upper()}_HISTORY_ROW_INVALID")
        if str(raw.get("team_id") or "") != expected_team_id:
            raise ValueError(f"CANONICAL_{side.upper()}_HISTORY_TEAM_MISMATCH")
        observed = _utc(raw.get("kickoff_utc"))
        if observed >= kickoff:
            raise ValueError(f"CANONICAL_{side.upper()}_HISTORY_LEAKAGE")
        gf, ga = raw.get("goals_for"), raw.get("goals_against")
        if (
            isinstance(gf, bool) or isinstance(ga, bool)
            or not isinstance(gf, int) or not isinstance(ga, int)
            or gf < 0 or ga < 0
        ):
            raise ValueError(f"CANONICAL_{side.upper()}_HISTORY_GOALS_INVALID")
        output.append((gf, ga))
    return output[:MAX_TEAM_HISTORY]


def _inputs_for_target(group_rows: list[dict[str, Any]], target: Mapping[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    kickoff = _utc(target["kickoff_utc"])
    prior = [r for r in group_rows if r["kickoff_utc"] < kickoff]
    if len(prior) < MIN_GROUP_BASELINE_HISTORY:
        return None, "BLOCKED_GROUP_HISTORY_BELOW_20"
    home_id, away_id = str(target["home_team_id"]), str(target["away_team_id"])
    by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in prior:
        by_team[row["home_team_id"]].append(row)
        by_team[row["away_team_id"]].append(row)

    raw_home_hist = by_team[home_id][-MAX_TEAM_HISTORY:]
    raw_away_hist = by_team[away_id][-MAX_TEAM_HISTORY:]
    canonical_home_hist = _canonical_team_history(target, "home", kickoff)
    canonical_away_hist = _canonical_team_history(target, "away", kickoff)

    if len(canonical_home_hist) >= MIN_TEAM_HISTORY:
        home_pairs = canonical_home_hist
        home_history_source = "CANONICAL_ENRICHED_PIT"
    else:
        home_pairs = [_team_view(r, home_id) for r in raw_home_hist]
        home_history_source = "RAW_GROUP_PIT"
    if len(canonical_away_hist) >= MIN_TEAM_HISTORY:
        away_pairs = canonical_away_hist
        away_history_source = "CANONICAL_ENRICHED_PIT"
    else:
        away_pairs = [_team_view(r, away_id) for r in raw_away_hist]
        away_history_source = "RAW_GROUP_PIT"

    if len(home_pairs) < MIN_TEAM_HISTORY:
        return None, "BLOCKED_HOME_TEAM_HISTORY_BELOW_5"
    if len(away_pairs) < MIN_TEAM_HISTORY:
        return None, "BLOCKED_AWAY_TEAM_HISTORY_BELOW_5"

    hgf = [x[0] for x in home_pairs]
    hga = [x[1] for x in home_pairs]
    agf = [x[0] for x in away_pairs]
    aga = [x[1] for x in away_pairs]
    hl = min(5.0, max(0.05, (_mean(hgf) + _mean(aga))/2.0))
    al = min(5.0, max(0.05, (_mean(agf) + _mean(hga))/2.0))
    pp = _score_probs(hl, al)
    n = len(prior)
    baseline = {
        "1x2": {
            "H": sum(r["home_goals"] > r["away_goals"] for r in prior)/n,
            "D": sum(r["home_goals"] == r["away_goals"] for r in prior)/n,
            "A": sum(r["home_goals"] < r["away_goals"] for r in prior)/n,
        },
        "over_2_5": sum(r["home_goals"] + r["away_goals"] >= 3 for r in prior)/n,
    }
    return {
        "prior_group_fixture_count": n,
        "home_history_count": len(home_pairs),
        "away_history_count": len(away_pairs),
        "home_history_source": home_history_source,
        "away_history_source": away_history_source,
        "expected_home_goals": round(hl, 8),
        "expected_away_goals": round(al, 8),
        "poisson": pp,
        "baseline": baseline,
    }, None


def _pool_1x2(poisson: Mapping[str, float], baseline: Mapping[str, float]) -> dict[str, float]:
    scores = {}
    for k in ("H", "D", "A"):
        scores[k] = exp(PARAMS_1X2["a"]*log(max(float(poisson[k]), EPS)) + PARAMS_1X2["c"]*log(max(float(baseline[k]), EPS)))
    total = sum(scores.values())
    return {k: scores[k]/total for k in ("H", "D", "A")}


def _pool_over25(poisson: float, baseline: float) -> float:
    return _sigmoid(PARAMS_OVER25["a"]*_logit(poisson) + PARAMS_OVER25["c"]*_logit(baseline) + PARAMS_OVER25["b"])


def build_shadow_p_matrix(*, canonical_bundle: Mapping[str, Any], canonical_manifest: Mapping[str, Any], raw_dir: Path, generated_at: datetime) -> dict[str, Any]:
    if canonical_manifest.get("status") != "PASS" or canonical_manifest.get("real_money") != "BLOCKED":
        raise ValueError("CANONICAL_GOVERNANCE_INVALID")
    if canonical_manifest.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("SOURCE_P_MATRIX_ALREADY_GENERATED")
    rows = canonical_bundle.get("inputs")
    if not isinstance(rows, list):
        raise ValueError("CANONICAL_INPUTS_MISSING")

    cache: dict[tuple[str, int], tuple[list[dict[str, Any]], str] | None] = {}
    scored, blocked = [], []
    for target in rows:
        league_id, season = str(target.get("competition_id") or ""), target.get("season")
        if not league_id or not isinstance(season, int):
            blocked.append({"target_key": target.get("target_key"), "reason": "BLOCKED_GROUP_IDENTITY_MISSING"})
            continue
        key = (league_id, season)
        if key not in cache:
            path = raw_dir / f"league_{league_id}_season_{season}.bin"
            cache[key] = _load_group(path) if path.is_file() else None
        group = cache[key]
        if group is None:
            blocked.append({"target_key": target.get("target_key"), "fixture_id": target.get("fixture_id"), "league_id": league_id, "season": season, "reason": "BLOCKED_RAW_GROUP_MISSING"})
            continue
        group_rows, raw_sha = group
        features, reason = _inputs_for_target(group_rows, target)
        if features is None:
            blocked.append({"target_key": target.get("target_key"), "fixture_id": target.get("fixture_id"), "league_id": league_id, "season": season, "reason": reason})
            continue
        p1 = _pool_1x2(features["poisson"]["1x2"], features["baseline"]["1x2"])
        po = _pool_over25(features["poisson"]["over_2_5"], features["baseline"]["over_2_5"])
        scored.append({
            "target_key": target["target_key"], "fixture_id": target["fixture_id"], "kickoff_utc": target["kickoff_utc"],
            "home_team": target.get("home_team_name"), "away_team": target.get("away_team_name"), "league_id": league_id, "season": season,
            "source_raw_group_sha256": raw_sha, "source_canonical_input_sha256": target.get("canonical_sha256"),
            "feature_counts": {k: features[k] for k in ("prior_group_fixture_count", "home_history_count", "away_history_count")},
            "history_sources": {"home": features["home_history_source"], "away": features["away_history_source"]},
            "expected_goals": {"home": features["expected_home_goals"], "away": features["expected_away_goals"]},
            "p_matrix_shadow": {"1x2": {k: round(p1[k], 10) for k in ("H", "D", "A")}, "over_2_5": round(po, 10)},
            "model": MODEL, "parameters": {"1x2": PARAMS_1X2, "over_2_5": PARAMS_OVER25},
            "btts_status": "BLOCKED_FINAL_HOLDOUT_NOT_SUPERIOR",
            "odds_used_to_generate_probability": False, "outcomes_used_from_target": False,
        })
    scored.sort(key=lambda r: (r["kickoff_utc"], r["fixture_id"]))
    blocked.sort(key=lambda r: (str(r.get("target_key")), str(r.get("reason"))))
    payload = {
        "schema": "MATRIX_FOOTBALL_MARKET_SCOPED_P_MATRIX_SHADOW_V1", "generated_at_utc": generated_at.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "model": MODEL, "source_canonical_bundle_sha256": canonical_manifest.get("bundle_sha256"), "source_ready_input_count": len(rows),
        "p_matrix_status": "GENERATED_SHADOW" if scored else "NOT_GENERATED", "scored_count": len(scored), "blocked_count": len(blocked),
        "markets_generated": ["1x2", "over_2_5"], "btts_status": "BLOCKED_FINAL_HOLDOUT_NOT_SUPERIOR",
        "rows": scored, "blocked": blocked,
        "protections": {"minimum_group_history": 20, "minimum_team_history": 5, "maximum_team_history": 20, "strictly_prior_kickoff_only": True, "canonical_enriched_pit_history_allowed": True, "raw_group_history_fallback_allowed": True, "parameter_refit": False, "parameter_search": False, "final_holdout_reused": False, "odds_used_to_generate_probability": False, "target_outcomes_used": False, "automatic_wagering": False, "real_money": "BLOCKED"},
    }
    payload["bundle_sha256"] = _canonical_hash({k: v for k, v in payload.items() if k != "bundle_sha256"})
    return payload


def main() -> None:
    root = Path("evidence/api_football/prospective_daily/2026-10-06/20261005T122152Z")
    canonical_bundle, canonical_manifest = load_chunked_canonical_bundle(root / "canonical_analysis")
    payload = build_shadow_p_matrix(canonical_bundle=canonical_bundle, canonical_manifest=canonical_manifest, raw_dir=root / "history/raw", generated_at=datetime.now(timezone.utc))
    out = root / "p_matrix_shadow"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "p_matrix_shadow.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: payload[k] for k in ("p_matrix_status", "scored_count", "blocked_count", "bundle_sha256")}, sort_keys=True))
    if payload["scored_count"] <= 0:
        raise SystemExit("NO_ELIGIBLE_SHADOW_P_MATRIX_ROWS")


if __name__ == "__main__":
    main()
