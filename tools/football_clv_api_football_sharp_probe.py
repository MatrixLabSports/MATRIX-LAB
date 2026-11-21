from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from app.research.football.prospective_ledger import (
    ClosingOddsReference,
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
)
from tools.football_clv_tracking_cycle import (
    API_BASE,
    DEFAULT_LEDGER,
    MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
    _aware,
)

BOOKMAKERS = ((3, "Betfair"), (4, "Pinnacle"))
OUT = Path("evidence/clv/football/over_2_5/api_football_sharp_transport_probe_latest.json")


def _existing(ledger):
    decisions=[]
    closed=set()
    for event in ledger.load_events():
        if event.event_type=="DECISION_FROZEN":
            decisions.append(FrozenProspectiveDecision.from_mapping(event.payload))
        elif event.event_type=="CLOSING_ODDS_RECORDED":
            closed.add(ClosingOddsReference.from_mapping(event.payload).decision_id)
    return decisions, closed


def _extract(payload: Mapping[str, Any], bookmaker_id: int, bookmaker_name: str):
    errors=payload.get("errors")
    if errors not in ({}, [], None):
        return None
    for fixture_row in payload.get("response") or []:
        if not isinstance(fixture_row, Mapping):
            continue
        update_raw=str(fixture_row.get("update") or "").strip()
        if not update_raw:
            continue
        provider_update=_aware(update_raw,name="PROVIDER_UPDATE")
        for bookmaker in fixture_row.get("bookmakers") or []:
            if not isinstance(bookmaker, Mapping):
                continue
            if str(bookmaker.get("id"))!=str(bookmaker_id):
                continue
            if str(bookmaker.get("name") or "").strip().casefold()!=bookmaker_name.casefold():
                continue
            for bet in bookmaker.get("bets") or []:
                if not isinstance(bet, Mapping):
                    continue
                try:
                    bet_id=int(bet.get("id"))
                except Exception:
                    continue
                if bet_id!=5:
                    continue
                over=under=None
                for value in bet.get("values") or []:
                    if not isinstance(value, Mapping):
                        continue
                    label=str(value.get("value") or "").strip().casefold()
                    try:
                        price=float(value.get("odd"))
                    except Exception:
                        continue
                    if price<=1.0:
                        continue
                    if label=="over 2.5":
                        over=price
                    elif label=="under 2.5":
                        under=price
                if over is not None and under is not None:
                    return over,under,provider_update
    return None


def run(api_key: str, out: Path = OUT, session=None):
    key=str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    ledger=FootballProspectiveEvidenceLedger(DEFAULT_LEDGER)
    decisions,closed=_existing(ledger)
    now=datetime.now(timezone.utc).replace(microsecond=0)
    future=[]
    for d in decisions:
        if d.decision_id in closed:
            continue
        kickoff=_aware(d.fixture_kickoff_utc,name="KICKOFF")
        if kickoff>now:
            future.append((kickoff,d))
    future.sort(key=lambda x:(x[0],x[1].fixture_id))
    targets=future[:5]
    client=session or requests.Session()
    rows=[]
    calls=0
    for kickoff,d in targets:
        row={
            "fixture_id":d.fixture_id,
            "decision_id":d.decision_id,
            "kickoff_utc":kickoff.isoformat(),
            "seconds_to_kickoff":int((kickoff-now).total_seconds()),
            "bookmakers":{},
        }
        for bookmaker_id,bookmaker_name in BOOKMAKERS:
            response=client.get(
                API_BASE+"/odds",
                headers={"x-apisports-key":key},
                params={"fixture":d.fixture_id,"bookmaker":bookmaker_id},
                timeout=(10,30),
            )
            calls+=1
            try:
                payload=response.json()
            except Exception:
                payload={}
            parsed=_extract(payload,bookmaker_id,bookmaker_name) if response.status_code<300 and isinstance(payload,Mapping) else None
            if parsed is None:
                row["bookmakers"][bookmaker_name]={
                    "bookmaker_id":bookmaker_id,
                    "http_status":int(response.status_code),
                    "complete_over_under_2_5":False,
                    "provider_quote_age_seconds":None,
                    "strict_120s_fresh":False,
                }
                continue
            over,under,provider_update=parsed
            age=int((now-provider_update).total_seconds())
            row["bookmakers"][bookmaker_name]={
                "bookmaker_id":bookmaker_id,
                "http_status":int(response.status_code),
                "complete_over_under_2_5":True,
                "provider_quote_updated_at_utc":provider_update.isoformat(),
                "provider_quote_age_seconds":age,
                "strict_120s_fresh":bool(0<=age<=MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS),
                "over_2_5_decimal_odds":over,
                "under_2_5_decimal_odds":under,
            }
        rows.append(row)
    summary={}
    for _,name in BOOKMAKERS:
        valid=[r["bookmakers"][name] for r in rows if r["bookmakers"].get(name,{}).get("complete_over_under_2_5")]
        fresh=[x for x in valid if x.get("strict_120s_fresh")]
        ages=[x["provider_quote_age_seconds"] for x in valid if isinstance(x.get("provider_quote_age_seconds"),int)]
        summary[name]={
            "targets":len(rows),
            "complete_market_count":len(valid),
            "strict_fresh_count":len(fresh),
            "min_quote_age_seconds":min(ages) if ages else None,
            "max_quote_age_seconds":max(ages) if ages else None,
        }
    payload={
        "schema":"MATRIX_FOOTBALL_CLV_API_FOOTBALL_SHARP_TRANSPORT_PROBE_V1",
        "generated_at_utc":now.isoformat(),
        "strict_fresh_gate_seconds":MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
        "candidate_bookmakers":[{"id":i,"name":n} for i,n in BOOKMAKERS],
        "target_count":len(rows),
        "network_calls":calls,
        "results":rows,
        "summary":summary,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return payload


def main():
    result=run(os.environ.get("API_FOOTBALL_KEY",""))
    print(json.dumps({"summary":result["summary"],"target_count":result["target_count"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
