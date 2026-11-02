"""Independent German/English/Spanish cup scoreboard corroboration (research only).

Use ESPN's publicly accessible league scoreboards, no assumed API-Football IDs,
no bookmaker data, no frozen predictor changes and no canonical append.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.request import Request,urlopen

from tools.matrix_13_cohort_espn_mls_results import compare,dt,BOGOTA,ROOT,DIR

TRIAGE=ROOT/"evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"
OUT=DIR/"MATRIX_ESPN_CUPS_EXACT_FINAL_LAST.json"
LEAGUES={
    "Copa del Rey":"esp.copa_del_rey",
    "DFB Pokal":"ger.dfb_pokal",
    "League Cup":"eng.league_cup",
}
URL="https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard?dates={day}"
MAX_BYTES=3_000_000

def run(rows,*,opener=urlopen):
    filtered=[x for x in rows if x.get("competition_name") in LEAGUES]
    keys=sorted({(x["competition_name"],dt(x["kickoff_utc"]).astimezone(BOGOTA).strftime("%Y%m%d")) for x in filtered})
    report={
        "schema":"MATRIX_ESPN_3_CUPS_EXACT_FINAL_V1",
        "status":"NO_CUP_QUEUE",
        "target_count":len(filtered),"queries_scheduled":[{"competition":c,"date":day} for c,day in keys],
        "network_calls":0,"exact_final_matches":0,"matched":[],"rejected":[],
        "canonical_ledger_appends":0,"telegram_authorized":False,
        "half_time_certified":False,"automatic_wagering":False,"real_money":"BLOCKED",
    }
    blobs={}
    if len(keys)>8:
        report["status"]="TOO_MANY_QUERIES"
        return report,blobs
    for competition,day in keys:
        uri=URL.format(slug=LEAGUES[competition],day=day)
        report["network_calls"]+=1
        try:
            req=Request(uri,headers={"Accept":"application/json","User-Agent":"MATRIX-Cohort-Evidence/1.0"})
            with opener(req,timeout=25) as response:
                body=response.read(MAX_BYTES+1)
                code=int(response.status)
            if code!=200 or len(body)>MAX_BYTES:
                report["rejected"].append({"competition":competition,"day":day,"reason":"HTTP_OR_SIZE_ERROR","status":code})
                continue
            payload=json.loads(body)
            sha=hashlib.sha256(body).hexdigest()
            group=[x for x in filtered if x.get("competition_name")==competition
                and dt(x["kickoff_utc"]).astimezone(BOGOTA).strftime("%Y%m%d")==day]
            accepted,rejected=compare(group,payload,sha)
            archive="ESPN_CUP_"+LEAGUES[competition].replace(".","_")+"_"+day+"_RAW.json"
            for a in accepted:
                a["competition_name"]=competition
                a["independent_source"]="ESPN_"+LEAGUES[competition]
                a["raw_archive_path"]="evidence/football_cohort_recovery/"+archive
            report["matched"].extend(accepted)
            report["rejected"].extend([{**x,"competition":competition,"day":day} for x in rejected])
            report.setdefault("source_response_sha256",{})[competition+"|"+day]=sha
            report.setdefault("provider_event_count",{})[competition+"|"+day]=len(payload["events"])
            blobs[archive]=body
        except HTTPError as e:
            report["rejected"].append({"competition":competition,"day":day,"reason":"HTTP_ERROR","status":int(e.code)})
        except (URLError,OSError,TimeoutError):
            report["rejected"].append({"competition":competition,"day":day,"reason":"NETWORK_ERROR"})
        except (ValueError,TypeError,KeyError,UnicodeError):
            report["rejected"].append({"competition":competition,"day":day,"reason":"INVALID_SCHEMA"})
    report["exact_final_matches"]=len(report["matched"])
    report["status"]="VERIFIED_INDEPENDENT_RESEARCH_ONLY" if report["matched"] else "NO_EXACT_FINAL_VERIFIED"
    return report,blobs


def main():
    t=json.loads(TRIAGE.read_text(encoding="utf-8"))
    if t.get("target_market_count")!=13 or t.get("protections",{}).get("real_money")!="BLOCKED":
        raise SystemExit("UNTRUSTED_TRIAGE")
    report,blobs=run(t["unsettled_fixture_triage"])
    DIR.mkdir(parents=True,exist_ok=True)
    for filename,body in blobs.items():
        (DIR/filename).write_bytes(body)
    OUT.write_text(json.dumps(report,sort_keys=True,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"queued":report["target_count"],
         "exact_matches":report["exact_final_matches"],"calls":report["network_calls"],
         "provider_events":report.get("provider_event_count")},sort_keys=True))


if __name__=="__main__":
    main()
