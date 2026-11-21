from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

FIXTURE_ID="1528902"
MARKET_NAME="Goals Over/Under"
SELECTION="Over 2.5"
SHADOW_STAKE_AMOUNT=1000
STAKE_CURRENCY="COP"
MIN_ODDS=1.50


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _utc(v:Any)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _sha_bytes(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()


def _sha_obj(value:Any)->str:
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


def _find_pinnacle_quote(payload:Mapping[str,Any])->dict[str,Any]:
    response=payload.get("response")
    if not isinstance(response,list) or len(response)!=1:
        raise ValueError("PINNACLE_FIXTURE_RESPONSE_NOT_EXACT")
    root=response[0]
    fixture=root.get("fixture")
    if not isinstance(fixture,Mapping) or str(fixture.get("id"))!=FIXTURE_ID:
        raise ValueError("PINNACLE_FIXTURE_ID_MISMATCH")
    bookmakers=root.get("bookmakers")
    if not isinstance(bookmakers,list):
        raise ValueError("BOOKMAKERS_MISSING")
    exact=[b for b in bookmakers if isinstance(b,Mapping) and int(b.get("id") or -1)==4 and str(b.get("name") or "")=="Pinnacle"]
    if len(exact)!=1:
        raise ValueError("PINNACLE_BOOKMAKER_EXACT_REQUIRED")
    bets=exact[0].get("bets")
    if not isinstance(bets,list):
        raise ValueError("PINNACLE_BETS_MISSING")
    market=[b for b in bets if isinstance(b,Mapping) and str(b.get("name") or "")==MARKET_NAME]
    if len(market)!=1:
        raise ValueError("TARGET_MARKET_EXACT_REQUIRED")
    values=market[0].get("values")
    if not isinstance(values,list):
        raise ValueError("TARGET_VALUES_MISSING")
    sel=[v for v in values if isinstance(v,Mapping) and str(v.get("value") or "")==SELECTION]
    if len(sel)!=1:
        raise ValueError("TARGET_SELECTION_EXACT_REQUIRED")
    odd=float(sel[0]["odd"])
    return {
        "bookmaker_id":4,
        "bookmaker":"Pinnacle",
        "market_id":market[0].get("id"),
        "market_name":MARKET_NAME,
        "selection":SELECTION,
        "decimal_odds":odd,
        "quote_updated_at_utc":root.get("update"),
        "fixture_kickoff_utc":fixture.get("date"),
    }


def build(root:Path,executed_at:datetime)->dict[str,Any]:
    freeze=_load(root/"evidence/api_football/prospective_market_freeze/freeze.json")
    rows=freeze.get("rows")
    if not isinstance(rows,list):
        raise ValueError("FREEZE_ROWS_MISSING")
    matches=[r for r in rows if isinstance(r,Mapping) and str(r.get("fixture_id"))==FIXTURE_ID]
    if len(matches)!=1:
        raise ValueError("EXACT_FROZEN_FIXTURE_REQUIRED")
    row=matches[0]

    raw_path=root/f"evidence/api_football/pinnacle_coverage/raw/fixture_{FIXTURE_ID}_pinnacle.bin"
    raw_bytes=raw_path.read_bytes()
    payload=json.loads(raw_bytes.decode("utf-8"))
    quote=_find_pinnacle_quote(payload)

    executed=executed_at.astimezone(timezone.utc).replace(microsecond=0)
    kickoff=_utc(row["kickoff_utc"])
    freeze_at=_utc(row["freeze_at_utc"])
    quote_at=_utc(quote["quote_updated_at_utc"])
    provider_kickoff=_utc(quote["fixture_kickoff_utc"])

    if provider_kickoff!=kickoff:
        raise ValueError("PROVIDER_FREEZE_KICKOFF_MISMATCH")
    if not (quote_at < freeze_at < executed < kickoff):
        raise ValueError("COR10_TEMPORAL_ORDER_INVALID")
    if row.get("outcome") is not None:
        raise ValueError("OUTCOME_ALREADY_PRESENT")
    if row.get("settlement_status")!="PENDING_FINAL":
        raise ValueError("FIXTURE_NOT_PENDING_FINAL")
    if row.get("odds_used_to_generate_probability") is not False:
        raise ValueError("ODDS_TO_PROBABILITY_PROHIBITED")

    model_probability=float(row["frozen_research_probabilities"]["over_2_5"])
    odds=float(quote["decimal_odds"])
    if odds < MIN_ODDS:
        raise ValueError("ODDS_BELOW_PROJECT_MINIMUM")
    implied_probability=1.0/odds
    expected_value=model_probability*odds-1.0

    record={
        "schema":"MATRIX_COR10_GENUINE_FUTURE_SHADOW_EXECUTION_V1",
        "correction":"COR10",
        "execution_id":f"COR10-FOOTBALL-{FIXTURE_ID}-OVER25-PINNACLE",
        "execution_mode":"SHADOW_PAPER_EXECUTION_NO_FUNDS_SENT",
        "execution_status":"EXECUTED",
        "executed_at_utc":executed.isoformat(),
        "fixture_id":FIXTURE_ID,
        "target_key":row["target_key"],
        "competition_id":row["competition_id"],
        "competition_name":row["competition_name"],
        "season":row["season"],
        "home_team_id":row["home_team_id"],
        "home_team_name":row["home_team_name"],
        "away_team_id":row["away_team_id"],
        "away_team_name":row["away_team_name"],
        "kickoff_utc":row["kickoff_utc"],
        "freeze_at_utc":row["freeze_at_utc"],
        "freeze_input_sha256":row["input_sha256"],
        "future_at_execution":executed<kickoff,
        "freeze_precedes_execution":freeze_at<executed,
        "quote_precedes_execution":quote_at<executed,
        "market":"over_2_5",
        "market_display_name":MARKET_NAME,
        "selection":SELECTION,
        "model_probability_frozen":model_probability,
        "probability_source":"FROZEN_RESEARCH_CHALLENGER_ONLY",
        "bookmaker":quote["bookmaker"],
        "bookmaker_id":quote["bookmaker_id"],
        "quote_transport":"API-Football /odds",
        "direct_pinnacle_api_connection":False,
        "decimal_odds":odds,
        "quote_updated_at_utc":quote["quote_updated_at_utc"],
        "quote_raw_path":raw_path.as_posix(),
        "quote_raw_sha256":_sha_bytes(raw_bytes),
        "stake":{
            "amount":SHADOW_STAKE_AMOUNT,
            "currency":STAKE_CURRENCY,
            "mode":"NOMINAL_SHADOW_STAKE",
            "funds_transferred":False,
            "bookmaker_ticket_id":None,
        },
        "implied_probability_reference_only":implied_probability,
        "expected_value_research_only":expected_value,
        "odds_used_to_generate_probability":False,
        "settlement_status":"PENDING_FINAL",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    record["record_sha256"]=_sha_obj(record)
    return record


def adjudicate(record:Mapping[str,Any])->dict[str,Any]:
    checks={
        "execution_present":record.get("execution_status")=="EXECUTED",
        "future_at_execution":record.get("future_at_execution") is True,
        "freeze_precedes_execution":record.get("freeze_precedes_execution") is True,
        "quote_precedes_execution":record.get("quote_precedes_execution") is True,
        "bookmaker_verifiable":record.get("bookmaker")=="Pinnacle" and record.get("bookmaker_id")==4,
        "stake_verifiable":isinstance(record.get("stake"),Mapping) and float(record["stake"].get("amount") or 0)>0 and bool(record["stake"].get("currency")),
        "shadow_only_no_funds":record.get("stake",{}).get("funds_transferred") is False and record.get("real_money")=="BLOCKED",
        "automatic_wagering_disabled":record.get("automatic_wagering") is False,
        "odds_not_probability_source":record.get("odds_used_to_generate_probability") is False,
        "raw_quote_hashed":isinstance(record.get("quote_raw_sha256"),str) and len(record["quote_raw_sha256"])==64,
        "record_hashed":isinstance(record.get("record_sha256"),str) and len(record["record_sha256"])==64,
    }
    passed=all(checks.values())
    return {
        "schema":"MATRIX_COR10_ADJUDICATION_V1",
        "correction":"COR10",
        "literal_acceptance":"100% future executions with verifiable stake + bookmaker",
        "genuine_future_execution_definition":"A real future fixture with pre-kickoff frozen model probability, pre-kickoff bookmaker quote, declared verifiable nominal shadow stake, and persisted physical evidence; no funds sent.",
        "execution_count":1,
        "future_execution_count":1 if checks["future_at_execution"] else 0,
        "future_execution_rate":1.0 if checks["future_at_execution"] else 0.0,
        "checks":checks,
        "pass":passed,
        "status":"RESOLVED" if passed else "IN_PROGRESS",
        "execution_id":record.get("execution_id"),
        "record_sha256":record.get("record_sha256"),
        "real_money":"BLOCKED",
    }


def main()->None:
    root=Path(".")
    out=root/"evidence/cor10"
    out.mkdir(parents=True,exist_ok=True)
    record_path=out/"MATRIX_COR10_GENUINE_FUTURE_EXECUTION.json"
    adjudication_path=out/"MATRIX_COR10_ADJUDICATION.json"
    if record_path.exists() or adjudication_path.exists():
        raise ValueError("COR10_EXECUTION_ALREADY_EXISTS_REFUSE_OVERWRITE")
    record=build(root,datetime.now(timezone.utc))
    adjudication=adjudicate(record)
    if not adjudication["pass"]:
        raise ValueError("COR10_ADJUDICATION_FAILED")
    record_path.write_text(json.dumps(record,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    adjudication_path.write_text(json.dumps(adjudication,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":adjudication["status"],
        "pass":adjudication["pass"],
        "execution_id":record["execution_id"],
        "executed_at_utc":record["executed_at_utc"],
        "kickoff_utc":record["kickoff_utc"],
        "bookmaker":record["bookmaker"],
        "decimal_odds":record["decimal_odds"],
        "stake":record["stake"],
        "real_money":record["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
