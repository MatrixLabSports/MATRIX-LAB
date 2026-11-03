"""Quarantine observed free-provider football events as research-only evidence."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

def bridge(observation: dict, target_date: str) -> dict:
    if observation.get("target_date") != target_date:
        raise ValueError("OBSERVATION_TARGET_DATE_MISMATCH_FAIL_CLOSED")
    if observation.get("source") != "TheSportsDB":
        raise ValueError("OBSERVATION_PROVIDER_MISMATCH_FAIL_CLOSED")
    rows=[]
    for event in observation.get("events", []):
        if not isinstance(event, dict) or event.get("status") != "NS":
            continue
        if not all(event.get(k) for k in ("idEvent", "home", "away")):
            continue
        rows.append({
            "source": "THESPORTSDB",
            "source_event_id": str(event["idEvent"]),
            "api_football_crossref_id": str(event.get("idAPIfootball") or ""),
            "home": str(event["home"]),
            "away": str(event["away"]),
            "league": str(event.get("league") or ""),
            "target_date_bogota": target_date,
            "status": "RESEARCH_ONLY_SOURCE_EVENT",
            "kickoff_certified": False,
            "sofascore_flashscore_reconciled": False,
            "p_matrix_status": "NOT_GENERATED",
            "exact_bookmaker_quote_status": "NOT_VERIFIED",
            "signal_generation_authorized": False
        })
    return {
        "schema": "MATRIX_FOOTBALL_FREE_FIXTURE_BRIDGE_V1",
        "target_date_bogota": target_date,
        "source": "THESPORTSDB",
        "source_observation_worldwide_complete": False,
        "research_event_count": len(rows),
        "research_events": rows,
        "canonical_producer_input_authorized": False,
        "telegram_signal_authorized": False,
        "status": "RESEARCH_ONLY_AWAIT_BROWSER_CROSSCHECK",
        "real_money": "BLOCKED",
        "automatic_wagering": False
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("evidence/governance/MATRIX_THESPORTSDB_20261101_BROWSER_OBSERVATION.json"))
    p.add_argument("--date",default="2026-11-01")
    p.add_argument("--out",type=Path,default=Path("evidence/governance/MATRIX_FOOTBALL_FREE_RESEARCH_EVENTS_LAST.json"))
    a=p.parse_args()
    result=bridge(json.loads(a.input.read_text(encoding="utf-8")),a.date)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"research_event_count":result["research_event_count"]}))
if __name__=="__main__":main()
