"""Isolated research scoring from independently sourced, current-season goal history.

Calls the ORIGINAL frozen Over 2.5 mathematical functions. Never promotes an
alternative provider into the trained production cohort without parity evidence.
No odds or Telegram calls; original MATRIX producer remains unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools.api_football_market_shadow_p_matrix import (
    PARAMS_OVER25, _inputs_for_target, _pool_over25,
)

MAX_HISTORY_CALLS = 6
MAX_BODY = 3_000_000
BASE = "https://api.football-data.org/v4/competitions"

def historic_rows(payload: dict, competition_id: int) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
        raise ValueError("HISTORY_MATCHES_ARRAY_REQUIRED")
    rows, seen = [], set()
    for raw in payload["matches"]:
        if not isinstance(raw, dict) or raw.get("status") != "FINISHED":
            continue
        competition = raw.get("competition") or payload.get("competition") or {}
        if str(competition.get("id")) != str(competition_id):
            raise ValueError("HISTORY_COMPETITION_IDENTITY_MISMATCH")
        home, away = raw.get("homeTeam") or {}, raw.get("awayTeam") or {}
        score = (raw.get("score") or {}).get("fullTime") or {}
        if not isinstance(score, dict):
            continue
        hg, ag = score.get("home"), score.get("away")
        if (isinstance(hg, bool) or isinstance(ag, bool) or
                not isinstance(hg, int) or not isinstance(ag, int) or
                hg < 0 or ag < 0):
            continue
        try:
            fid = str(int(raw["id"]))
            home_id, away_id = str(int(home["id"])), str(int(away["id"]))
            utc = datetime.fromisoformat(str(raw["utcDate"]).replace("Z", "+00:00"))
            if utc.tzinfo is None:
                continue
            utc = utc.astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        if fid in seen or home_id == away_id:
            raise ValueError("HISTORICAL_DUPLICATE_OR_INVALID_ID")
        seen.add(fid)
        rows.append({"fixture_id": fid, "kickoff_utc": utc,
                     "home_team_id": home_id, "away_team_id": away_id,
                     "home_goals": hg, "away_goals": ag})
    return sorted(rows, key=lambda r: (r["kickoff_utc"], r["fixture_id"]))

def score_intake(intake: dict, token: str, *, opener=urlopen) -> dict:
    if intake.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1":
        raise ValueError("UNTRUSTED_INTAKE_SCHEMA")
    if intake.get("source") != "FOOTBALL_DATA_ORG" or intake.get("real_money") != "BLOCKED":
        raise ValueError("UNTRUSTED_INTAKE_PROVIDER_OR_GOVERNANCE")
    if intake.get("signal_generation_authorized") is not False:
        raise ValueError("INDEPENDENT_DISCOVERY_MUST_NOT_AUTHORIZE_SIGNALS")
    output = {
        "schema": "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1",
        "target_date_bogota": intake.get("target_date_bogota"),
        "status": "RESEARCH_ONLY_PENDING_PROVIDER_EQUIVALENCE_AND_QUOTES",
        "model": "calibrated_log_pool_v1",
        "frozen_parameters": dict(PARAMS_OVER25),
        "parameter_refit": False,
        "target_outcomes_used": False,
        "odds_used_to_generate_probability": False,
        "source": "FOOTBALL_DATA_ORG",
        "network_calls": 0, "scored": [], "blocked": [],
        "historical_source_equivalence_verified": False,
        "browser_identity_crosschecked": False,
        "market_signal_authorized": False,
        "telegram_sent": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    fixtures = intake.get("fixtures")
    if not isinstance(fixtures, list):
        raise ValueError("INTAKE_FIXTURES_MUST_BE_ARRAY")
    if not token or not fixtures:
        output["status"] = "BLOCKED_NO_TOKEN_OR_FIXTURES"
        return output
    groups: dict[str, dict] = {}
    for f in fixtures:
        cid = f.get("source_competition_id") if isinstance(f, dict) else None
        if isinstance(cid, bool) or not isinstance(cid, int) or cid <= 0:
            output["blocked"].append({"source_fixture_id": f.get("source_fixture_id") if isinstance(f, dict) else None,
                                      "reason": "COMPETITION_ID_NOT_CERTIFIED"})
            continue
        key = str(cid)
        if key in groups:
            continue
        if len(groups) >= MAX_HISTORY_CALLS:
            output["blocked"].append({"source_fixture_id": f.get("source_fixture_id"),
                                      "reason": "MAX_PROVIDER_HISTORY_CALLS_REACHED"})
            continue
        request = Request(BASE + "/" + key + "/matches",
                          headers={"X-Auth-Token": token, "Accept": "application/json"})
        output["network_calls"] += 1
        try:
            with opener(request, timeout=25) as response:
                status = int(response.status)
                body = response.read(MAX_BODY + 1)
            if status != 200 or len(body) > MAX_BODY:
                groups[key] = {"status": "HTTP_OR_SIZE_BLOCK", "rows": []}
                continue
            payload = json.loads(body.decode("utf-8"))
            rows = historic_rows(payload, cid)
            groups[key] = {"status": "HISTORY_CAPTURED", "rows": rows,
                           "sha256": hashlib.sha256(body).hexdigest(),
                           "history_count": len(rows)}
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, TypeError, KeyError) as exc:
            groups[key] = {"status": "HISTORY_PROVIDER_BLOCKED", "error_type": type(exc).__name__, "rows": []}
    output["group_status"] = {k: {z:v for z,v in group.items() if z!="rows"} for k,group in groups.items()}
    for f in fixtures:
        if not isinstance(f, dict):
            continue
        cid = str(f.get("source_competition_id") or "")
        group = groups.get(cid)
        fixture_id = f.get("source_fixture_id")
        if not group or group["status"] != "HISTORY_CAPTURED":
            output["blocked"].append({"source_fixture_id":fixture_id,"reason":"HISTORY_GROUP_NOT_AVAILABLE"})
            continue
        target = {"kickoff_utc": f.get("kickoff_utc"),
                  "home_team_id": f.get("home_source_team_id"),
                  "away_team_id": f.get("away_source_team_id")}
        try:
            features, reason = _inputs_for_target(group["rows"], target)
        except (ValueError, TypeError, KeyError) as exc:
            features, reason = None, "INVALID_PIT_FEATURES:" + type(exc).__name__
        if features is None:
            output["blocked"].append({"source_fixture_id": fixture_id, "reason": reason})
            continue
        probability = _pool_over25(
            float(features["poisson"]["over_2_5"]),
            float(features["baseline"]["over_2_5"]),
        )
        output["scored"].append({
            "source_fixture_id": fixture_id,
            "competition_id": int(cid),
            "home": f["home"], "away": f["away"],
            "kickoff_utc": f["kickoff_utc"],
            "p_over25_research": round(probability, 10),
            "feature_counts": {key: features[key] for key in (
                "prior_group_fixture_count", "home_history_count", "away_history_count"
            )},
            "history_sha256": group["sha256"],
            "provider_identity_crosswalk_verified": False,
            "calibrated_source_parity_verified": False,
            "signal_generation_authorized": False,
        })
    output["scored_count"] = len(output["scored"])
    output["blocked_count"] = len(output["blocked"])
    return output

def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--intake",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    input_data=json.loads(args.intake.read_text(encoding="utf-8"))
    output=score_intake(input_data,os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(output,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:output[k] for k in ("status","network_calls","scored_count","blocked_count","market_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
