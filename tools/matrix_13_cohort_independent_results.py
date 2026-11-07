"""One-call, authenticated, strict alternative-final source recovery for MATRIX.

Uses football-data.org independently from suspended API-Football. Only exact
home+away+UTC kickoff pairs; provider fixture IDs are NEVER equated by guess.
Immutable prospective freezes are not changed. Produces a research sidecar,
raw response audit and explicit blockers; does not append the canonical ledger.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
TRIAGE = ROOT / "evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"
DEST = ROOT / "evidence/football_cohort_recovery/MATRIX_INDEPENDENT_FINAL_RECONCILIATION_LAST.json"
RAW = ROOT / "evidence/football_cohort_recovery/FOOTBALL_DATA_ORG_RAW_LAST.json"
BASE = "https://api.football-data.org/v4/matches"
MAX_BYTES = 5_000_000
MAX_RANGE_DAYS = 15


def dt(v):
    d = datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if d.utcoffset() is None:
        raise ValueError("NAIVE_TIME")
    return d.astimezone(timezone.utc)


def normalized(v):
    if not isinstance(v,str) or not v.strip():
        raise ValueError("TEAM_NAME_MISSING")
    value = unicodedata.normalize("NFKD",v.strip()).casefold()
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+",value))


def _score(v):
    if type(v) is not int or v < 0:
        raise ValueError("SCORE_NOT_EXACT_NONNEGATIVE_INT")
    return v


def compare(queued, payload, *, source_sha256, captured_at_utc):
    if not isinstance(payload,dict) or not isinstance(payload.get("matches"),list):
        raise ValueError("PROVIDER_MATCHES_LIST_MISSING")
    indexed={}
    for match in payload["matches"]:
        if not isinstance(match,dict):
            continue
        try:
            start = dt(match["utcDate"]).isoformat()
            home = normalized(match["homeTeam"]["name"])
            away = normalized(match["awayTeam"]["name"])
        except (ValueError,KeyError,TypeError):
            continue
        indexed.setdefault((start,home,away),[]).append(match)
    matched=[]; rejected=[]; ambiguous=0
    for row in queued:
        fid=str(row.get("fixture_id") or "")
        try:
            start=dt(row["kickoff_utc"])
            frozen=dt(row["freeze_at_utc"])
            if not fid or frozen>=start:
                raise ValueError("MISSING_OR_POSTSTART_FREEZE")
            key=(start.isoformat(),normalized(row["home_team_name"]),normalized(row["away_team_name"]))
        except (ValueError,TypeError,KeyError):
            rejected.append({"fixture_id":fid,"reason":"INVALID_CANONICAL_FROZEN_IDENTITY"})
            continue
        candidates=indexed.get(key,[])
        if len(candidates)!=1:
            if len(candidates)>1: ambiguous+=1
            rejected.append({"fixture_id":fid,"reason":"NO_EXACT_CROSS_PROVIDER_IDENTITY" if not candidates else "AMBIGUOUS_CROSS_PROVIDER_IDENTITY"})
            continue
        m=candidates[0]
        if m.get("status")!="FINISHED":
            rejected.append({"fixture_id":fid,"reason":"INDEPENDENT_RESULT_NOT_FINISHED","provider_status":m.get("status")})
            continue
        score=m.get("score") or {}
        if score.get("duration") not in ("REGULAR","REGULAR_TIME"):
            rejected.append({"fixture_id":fid,"reason":"EXTRA_TIME_OR_UNKNOWN_SCORE_DURATION","duration":score.get("duration")})
            continue
        try:
            full=score["fullTime"]
            hg,ag=_score(full["home"]),_score(full["away"])
            ht=score.get("halfTime") or {}
            hh,ah=ht.get("home"),ht.get("away")
            half_ok=(type(hh) is int and type(ah) is int and 0<=hh<=hg and 0<=ah<=ag)
            if not half_ok: hh=ah=None
            provider_id=str(int(m["id"]))
        except (TypeError,ValueError,KeyError):
            rejected.append({"fixture_id":fid,"reason":"INDEPENDENT_SCORE_INVALID"})
            continue
        matched.append({
            "api_football_fixture_id":fid,
            "frozen_kickoff_utc":start.isoformat(),
            "frozen_home":row["home_team_name"],
            "frozen_away":row["away_team_name"],
            "independent_source":"FOOTBALL_DATA_ORG",
            "independent_provider_fixture_id":provider_id,
            "provider_home":m["homeTeam"]["name"],"provider_away":m["awayTeam"]["name"],
            "provider_status":m["status"],"score_duration":score["duration"],
            "fulltime_home":hg,"fulltime_away":ag,
            "halftime_home":hh,"halftime_away":ah,
            "halftime_certified":half_ok,
            "independent_raw_response_sha256":source_sha256,
            "captured_at_utc":captured_at_utc,
            "immutable_pre_match_prediction_required":True,
            "authorized_to_append_canonical_settlement":False,
            "authorized_to_produce_signals":False,
        })
    return matched,rejected,ambiguous


def capture(triage,token,*,opener=urlopen,now_utc=None):
    now=(now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    queued=triage.get("unsettled_fixture_triage") or []
    result={
        "schema":"MATRIX_13_COHORT_AUTHENTICATED_INDEPENDENT_FINAL_V1",
        "generated_at_utc":now.isoformat(),
        "status":"BLOCKED",
        "source":"FOOTBALL_DATA_ORG",
        "source_order":["SOFASCORE","FLASHSCORE","APIS"],
        "quota_bounded_provider_calls":0,
        "eligible_queued_fixtures":len(queued),
        "identity_matched_standard_final":0,
        "half_time_certified":0,
        "matched":[],
        "rejected":[],
        "no_fuzzy_identity_matching":True,
        "canonical_ledger_appends":0,
        "historical_prediction_changes":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "telegram_signal_authorized":False,
    }
    if not token.strip():
        result["status"]="TOKEN_UNAVAILABLE"
        return result,None
    dates=[]
    for row in queued:
        try:
            kickoff=dt(row["kickoff_utc"])
            if kickoff<=now: dates.append(kickoff.date())
        except (ValueError,TypeError,KeyError):
            continue
    if not dates:
        result["status"]="NO_DUE_EVENTS"
        return result,None
    first,last=min(dates),max(dates)+timedelta(days=1)
    if (last-first).days > MAX_RANGE_DAYS:
        result["status"]="DATE_RANGE_TOO_WIDE_FOR_ONE_CALL"
        return result,None
    params={"dateFrom":first.isoformat(),"dateTo":last.isoformat()}
    result["provider_request_scope"]=params
    request=Request(BASE+"?"+urlencode(params),headers={"X-Auth-Token":token,"Accept":"application/json"})
    result["quota_bounded_provider_calls"]=1
    try:
        with opener(request,timeout=30) as response:
            status=int(response.status)
            body=response.read(MAX_BYTES+1)
        result["http_status"]=status
        result["response_sha256"]=hashlib.sha256(body).hexdigest()
        result["response_bytes"]=len(body)
        if status!=200 or len(body)>MAX_BYTES:
            result["status"]="NON_200_OR_TOO_LARGE"
            return result,None
        payload=json.loads(body)
        matched,rejected,ambiguous=compare(queued,payload,source_sha256=result["response_sha256"],captured_at_utc=now.isoformat())
        result["matched"]=matched
        result["rejected"]=rejected
        result["ambiguous_matches"]=ambiguous
        result["identity_matched_standard_final"]=len(matched)
        result["half_time_certified"]=sum(x["halftime_certified"] for x in matched)
        result["source_match_count"]=len(payload.get("matches",[]))
        result["status"]="AUTHENTICATED_EXACT_IDENTITY_RESEARCH_ONLY"
        return result,body
    except HTTPError as e:
        result["http_status"]=int(e.code)
        result["status"]="HTTP_ERROR"
    except (URLError,OSError,TimeoutError):
        result["status"]="NETWORK_ERROR"
    except (UnicodeError,ValueError,TypeError,KeyError):
        result["status"]="INVALID_PROVIDER_RESPONSE"
    return result,None


def main():
    triage=json.loads(TRIAGE.read_text(encoding="utf-8"))
    if triage.get("target_market_count")!=13 or triage.get("protections",{}).get("real_money")!="BLOCKED":
        raise SystemExit("UNTRUSTED_TRIAGE_INPUT")
    result,body=capture(triage,os.environ.get("FOOTBALL_DATA_ORG_TOKEN",""))
    DEST.parent.mkdir(parents=True,exist_ok=True)
    if body is not None:
        RAW.write_bytes(body)
        assert hashlib.sha256(RAW.read_bytes()).hexdigest()==result["response_sha256"]
        result["raw_response_path"]=RAW.relative_to(ROOT).as_posix()
    DEST.write_text(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:result.get(k) for k in (
        "status","http_status","eligible_queued_fixtures","source_match_count",
        "identity_matched_standard_final","half_time_certified","quota_bounded_provider_calls"
    )},sort_keys=True))


if __name__=="__main__":
    main()
