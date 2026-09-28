from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from math import exp, factorial, log
from pathlib import Path
from typing import Any, Iterable, Mapping

FINAL_STATUSES = {"FT", "AET", "PEN"}
MIN_TEAM_HISTORY = 5
MAX_TEAM_HISTORY = 20
MIN_GROUP_BASELINE_HISTORY = 20
SCORE_CAP = 10
EPS = 1e-15


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _load_json_bytes(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_ROOT_MUST_BE_OBJECT:{path}")
    return value


def _fixture(raw: Mapping[str, Any], *, source_path: str) -> dict[str, Any] | None:
    fixture = raw.get("fixture")
    league = raw.get("league")
    teams = raw.get("teams")
    goals = raw.get("goals")
    if not all(isinstance(x, Mapping) for x in (fixture, league, teams, goals)):
        return None
    status = fixture.get("status")
    home = teams.get("home")
    away = teams.get("away")
    if not all(isinstance(x, Mapping) for x in (status, home, away)):
        return None
    if str(status.get("short") or "").upper().strip() not in FINAL_STATUSES:
        return None
    try:
        fixture_id = str(int(fixture.get("id")))
        home_id = str(int(home.get("id")))
        away_id = str(int(away.get("id")))
        kickoff = _utc(fixture.get("date"))
    except (TypeError, ValueError):
        return None
    hg, ag = goals.get("home"), goals.get("away")
    if isinstance(hg, bool) or isinstance(ag, bool) or not isinstance(hg, int) or not isinstance(ag, int):
        return None
    if hg < 0 or ag < 0:
        return None
    return {
        "fixture_id": fixture_id,
        "kickoff_utc": kickoff.isoformat(),
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_goals": hg,
        "away_goals": ag,
        "competition": str(league.get("name") or "").strip(),
        "league_id": str(league.get("id") or "").strip(),
        "season": league.get("season"),
        "source_path": source_path,
    }


def _mean(values: Iterable[int]) -> float:
    values = list(values)
    if not values:
        raise ValueError("MEAN_REQUIRES_VALUES")
    return sum(values) / len(values)


def _poisson(k: int, lam: float) -> float:
    return exp(-lam) * (lam ** k) / factorial(k)


def _score_probs(home_lambda: float, away_lambda: float) -> dict[str, float]:
    h = d = a = o25 = btts = mass = 0.0
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
            if hg > 0 and ag > 0:
                btts += p
    if mass <= 0:
        raise ValueError("INVALID_POISSON_MASS")
    return {
        "H": h / mass,
        "D": d / mass,
        "A": a / mass,
        "over_2_5": o25 / mass,
        "btts": btts / mass,
    }


def _team_view(row: Mapping[str, Any], team_id: str) -> tuple[int, int]:
    if row["home_team_id"] == team_id:
        return int(row["home_goals"]), int(row["away_goals"])
    if row["away_team_id"] == team_id:
        return int(row["away_goals"]), int(row["home_goals"])
    raise ValueError("TEAM_NOT_IN_FIXTURE")


def _binary_scores(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    if not rows:
        raise ValueError("NO_ROWS")
    brier = 0.0
    ll = 0.0
    for row in rows:
        p = float(row["poisson"][key])
        y = 1.0 if bool(row["outcome"][key]) else 0.0
        brier += (p-y)**2
        ll += -(y*log(min(max(p, EPS), 1-EPS)) + (1-y)*log(min(max(1-p, EPS), 1-EPS)))
    return {"sample_size": len(rows), "brier_score": brier/len(rows), "log_loss": ll/len(rows)}


def _multiclass_scores(rows: list[dict[str, Any]], source: str) -> dict[str, float]:
    if not rows:
        raise ValueError("NO_ROWS")
    brier = 0.0
    ll = 0.0
    correct = 0
    for row in rows:
        probs = row[source]["1x2"]
        actual = row["outcome"]["1x2"]
        for klass in ("H","D","A"):
            y = 1.0 if actual == klass else 0.0
            brier += (float(probs[klass])-y)**2
        ll += -log(max(float(probs[actual]), EPS))
        correct += int(max(("H","D","A"), key=lambda k: probs[k]) == actual)
    return {"sample_size": len(rows), "brier_score": brier/len(rows), "log_loss": ll/len(rows), "accuracy": correct/len(rows)}


def _binary_baseline_scores(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    brier = ll = 0.0
    for row in rows:
        p = float(row["baseline"][key])
        y = 1.0 if bool(row["outcome"][key]) else 0.0
        brier += (p-y)**2
        ll += -(y*log(min(max(p, EPS), 1-EPS)) + (1-y)*log(min(max(1-p, EPS), 1-EPS)))
    return {"sample_size": len(rows), "brier_score": brier/len(rows), "log_loss": ll/len(rows)}


def build_retrospective_walk_forward(raw_dir: Path) -> dict[str, Any]:
    files = sorted(raw_dir.glob("league_*_season_*.bin"))
    groups: list[dict[str, Any]] = []
    predictions: list[dict[str, Any]] = []
    total_final = 0
    duplicate_fixture_ids: set[str] = set()
    seen_fixture_ids: set[str] = set()

    for path in files:
        payload = _load_json_bytes(path)
        response = payload.get("response")
        if not isinstance(response, list):
            continue
        finals = [
            f for raw in response
            for f in [_fixture(raw, source_path=path.as_posix())]
            if f is not None
        ]
        finals.sort(key=lambda x: (x["kickoff_utc"], int(x["fixture_id"])))
        total_final += len(finals)
        group_predictions = 0

        prior: list[dict[str, Any]] = []
        by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for target in finals:
            fid = target["fixture_id"]
            if fid in seen_fixture_ids:
                duplicate_fixture_ids.add(fid)
                prior.append(target)
                by_team[target["home_team_id"]].append(target)
                by_team[target["away_team_id"]].append(target)
                continue
            seen_fixture_ids.add(fid)

            home_hist = by_team[target["home_team_id"]][-MAX_TEAM_HISTORY:]
            away_hist = by_team[target["away_team_id"]][-MAX_TEAM_HISTORY:]
            if len(home_hist) >= MIN_TEAM_HISTORY and len(away_hist) >= MIN_TEAM_HISTORY and len(prior) >= MIN_GROUP_BASELINE_HISTORY:
                hgf=[_team_view(r,target["home_team_id"])[0] for r in home_hist]
                hga=[_team_view(r,target["home_team_id"])[1] for r in home_hist]
                agf=[_team_view(r,target["away_team_id"])[0] for r in away_hist]
                aga=[_team_view(r,target["away_team_id"])[1] for r in away_hist]
                hl=min(5.0,max(0.05,(_mean(hgf)+_mean(aga))/2.0))
                al=min(5.0,max(0.05,(_mean(agf)+_mean(hga))/2.0))
                pp=_score_probs(hl,al)

                n=len(prior)
                base_h=sum(r["home_goals"]>r["away_goals"] for r in prior)/n
                base_d=sum(r["home_goals"]==r["away_goals"] for r in prior)/n
                base_a=sum(r["home_goals"]<r["away_goals"] for r in prior)/n
                base_o=sum(r["home_goals"]+r["away_goals"]>=3 for r in prior)/n
                base_b=sum(r["home_goals"]>0 and r["away_goals"]>0 for r in prior)/n

                actual="H" if target["home_goals"]>target["away_goals"] else "D" if target["home_goals"]==target["away_goals"] else "A"
                predictions.append({
                    "fixture_id":fid,
                    "kickoff_utc":target["kickoff_utc"],
                    "league_id":target["league_id"],
                    "season":target["season"],
                    "competition":target["competition"],
                    "home_history_count":len(home_hist),
                    "away_history_count":len(away_hist),
                    "prior_group_fixture_count":n,
                    "expected_home_goals":round(hl,8),
                    "expected_away_goals":round(al,8),
                    "poisson":{"1x2":{k:round(pp[k],10) for k in ("H","D","A")},"over_2_5":round(pp["over_2_5"],10),"btts":round(pp["btts"],10)},
                    "baseline":{"1x2":{"H":round(base_h,10),"D":round(base_d,10),"A":round(base_a,10)},"over_2_5":round(base_o,10),"btts":round(base_b,10)},
                    "outcome":{"1x2":actual,"over_2_5":target["home_goals"]+target["away_goals"]>=3,"btts":target["home_goals"]>0 and target["away_goals"]>0},
                    "source_path":target["source_path"],
                })
                group_predictions += 1

            prior.append(target)
            by_team[target["home_team_id"]].append(target)
            by_team[target["away_team_id"]].append(target)

        groups.append({
            "source_path":path.as_posix(),
            "final_fixture_count":len(finals),
            "eligible_prediction_count":group_predictions,
        })

    predictions.sort(key=lambda x:(x["kickoff_utc"],int(x["fixture_id"])))
    one_poisson=_multiclass_scores(predictions,"poisson") if predictions else None
    one_base=_multiclass_scores(predictions,"baseline") if predictions else None
    over_poisson=_binary_scores(predictions,"over_2_5") if predictions else None
    over_base=_binary_baseline_scores(predictions,"over_2_5") if predictions else None
    btts_poisson=_binary_scores(predictions,"btts") if predictions else None
    btts_base=_binary_baseline_scores(predictions,"btts") if predictions else None

    metrics={
        "1x2":{"poisson":one_poisson,"baseline":one_base},
        "over_2_5":{"poisson":over_poisson,"baseline":over_base},
        "btts":{"poisson":btts_poisson,"baseline":btts_base},
    }
    for market in metrics.values():
        if market["poisson"] and market["baseline"]:
            market["delta_brier_poisson_minus_baseline"]=market["poisson"]["brier_score"]-market["baseline"]["brier_score"]
            market["delta_log_loss_poisson_minus_baseline"]=market["poisson"]["log_loss"]-market["baseline"]["log_loss"]

    all_brier_better=bool(predictions) and all(v["delta_brier_poisson_minus_baseline"]<0 for v in metrics.values())
    all_log_better=bool(predictions) and all(v["delta_log_loss_poisson_minus_baseline"]<0 for v in metrics.values())
    enough_test=len(predictions)>=500

    return {
        "schema":"MATRIX_FOOTBALL_RETROSPECTIVE_WALK_FORWARD_VALIDATION_V1",
        "evaluation_kind":"RETROSPECTIVE_TEMPORAL_WALK_FORWARD_NOT_PROSPECTIVE",
        "source_provider":"api_football",
        "source_raw_group_count":len(files),
        "parsed_final_fixture_count":total_final,
        "eligible_prediction_count":len(predictions),
        "minimum_team_history":MIN_TEAM_HISTORY,
        "maximum_team_history":MAX_TEAM_HISTORY,
        "minimum_group_baseline_history":MIN_GROUP_BASELINE_HISTORY,
        "target_leakage_protection":"EACH_TARGET_USES_ONLY_FIXTURES_WITH_STRICTLY_EARLIER_KICKOFF_WITHIN_SAME_RAW_GROUP",
        "capture_limitation":"RAW_PAYLOADS_WERE_ACQUIRED_RETROSPECTIVELY_ON_2026-09-28; THIS_IS_NOT_PROSPECTIVE_EVIDENCE",
        "duplicate_fixture_ids_across_raw_groups":sorted(duplicate_fixture_ids),
        "metrics":metrics,
        "promotion_screen":{
            "minimum_test_samples_500_satisfied":enough_test,
            "poisson_beats_naive_baseline_all_markets_brier":all_brier_better,
            "poisson_beats_naive_baseline_all_markets_log_loss":all_log_better,
            "candidate_for_further_validation":enough_test and all_brier_better,
            "governed_engine_promoted":False,
            "p_matrix_generated":False,
            "paper_trading_satisfied":False,
            "odds_ev_validation_satisfied":False,
            "external_audit_closed":False,
        },
        "groups":groups,
        "predictions":predictions,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def _canonical_hash(payload: Mapping[str, Any]) -> str:
    return sha256(json.dumps(dict(payload),ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def main() -> None:
    root=Path(".")
    result=build_retrospective_walk_forward(root/"evidence/api_football/history/raw")
    out=root/"evidence/api_football/model_validation"
    out.mkdir(parents=True,exist_ok=True)
    predictions=result.pop("predictions")
    pred_payload={"schema":"MATRIX_FOOTBALL_RETROSPECTIVE_WALK_FORWARD_PREDICTIONS_V1","rows":predictions}
    pred_path=out/"retrospective_predictions.json"
    pred_path.write_text(json.dumps(pred_payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    result["predictions_sha256"]=_canonical_hash(pred_payload)
    result["predictions_path"]=pred_path.as_posix()
    result["generated_at_utc"]=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest=out/"retrospective_validation.json"
    manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "eligible_prediction_count":result["eligible_prediction_count"],
        "parsed_final_fixture_count":result["parsed_final_fixture_count"],
        "promotion_screen":result["promotion_screen"],
        "metrics":result["metrics"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
