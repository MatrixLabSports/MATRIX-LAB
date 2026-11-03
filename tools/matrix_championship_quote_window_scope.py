"""Research-only prematch odds scope sourced from genuine Championship PIT attestation.

Never converts independent research probabilities into original p_matrix.
No network calls; used before a separate quota-governed odds audit.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

def utc(value):
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("QUOTE_SCOPE_NEEDS_AWARE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)

def digest(d):
    return hashlib.sha256(json.dumps(d,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def index(rows,key):
    if not isinstance(rows,list): raise ValueError("QUOTE_SCOPE_ROWS_MISSING")
    output={}
    for row in rows:
        if not isinstance(row,dict) or not str(row.get(key) or ""):
            raise ValueError("QUOTE_SCOPE_ID_INVALID")
        id=str(row[key])
        if id in output:raise ValueError("QUOTE_SCOPE_DUPLICATE_ID")
        output[id]=row
    return output

def scope(intake,shadow,attestation,sofa,flash,*,now):
    clock=utc(now.isoformat())
    day=intake.get("target_date_bogota")
    for doc in (intake,shadow,attestation,sofa,flash):
        if doc.get("real_money")!="BLOCKED":
            raise ValueError("QUOTE_SCOPE_GOVERNANCE_NOT_BLOCKED")
        if doc.get("target_date_bogota")!=day:
            raise ValueError("QUOTE_SCOPE_DAY_MISMATCH")
    if (intake.get("schema")!="MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("provider_status")!="AUTHENTICATED_FIXTURE_CAPTURE"
        or shadow.get("schema")!="MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW_V1"
        or attestation.get("schema")!="MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION_V1"
        or not flash.get("flashscore_verified")
        or not flash.get("sofascore_verified")
        or any((intake.get("signal_generation_authorized") is not False,
                shadow.get("market_signal_authorized") is not False,
                attestation.get("telegram_signal_authorized") is not False))):
        raise ValueError("QUOTE_SCOPE_SOURCE_NOT_CERTIFIED")
    source_at=utc(intake["generated_at_utc"])
    attested_at=utc(attestation["observed_at_utc"])
    if not (0 <= (clock-source_at).total_seconds() <= 86400
            and source_at<=attested_at<=clock
            and (clock-attested_at).total_seconds()<=86400):
        raise ValueError("QUOTE_SCOPE_SOURCE_STALE")
    fixtures=index(intake.get("fixtures"),"source_fixture_id")
    scores=index(shadow.get("scored"),"source_fixture_id")
    evidence=index(attestation.get("rows"),"source_fixture_id")
    sofas=index(sofa.get("matched"),"fixture_id")
    flashes=index(flash.get("matched"),"source_fixture_id")
    selected=[]
    for fid,a in sorted(evidence.items()):
        if (a.get("status")!="PASS_PROSPECTIVE_RESEARCH_HISTORY_ONLY"
            or a.get("governed_probability_authorized") is not False
            or a.get("telegram_signal_authorized") is not False):
            continue
        f,score,b,c=fixtures.get(fid),scores.get(fid),sofas.get(fid),flashes.get(fid)
        if None in (f,score,b,c):
            continue
        if (f.get("source_competition_code")!="ELC"
            or str(f.get("source_competition_id"))!="2016"
            or str(score.get("kickoff_utc"))!=f.get("kickoff_utc")
            or a.get("kickoff_utc")!=f.get("kickoff_utc")
            or b.get("kickoff_utc")!=f.get("kickoff_utc")
            or c.get("kickoff_utc")!=f.get("kickoff_utc")
            or b.get("identity_time_and_teams_verified") is not True
            or c.get("three_source_calendar_identity_verified") is not True
            or str(b.get("sofascore_event_id") or "")!=str(c.get("sofascore_event_id") or "")
            or not c.get("flashscore_mid")):
            continue
        target=utc(f.get("kickoff_utc"))
        until=(target-clock).total_seconds()
        if not 0<until<=7200:
            continue
        if (utc(a["research_as_of_utc"])>=target
            or not a.get("research_source_history_sha256")
            or a.get("research_source_history_sha256")!=score.get("history_sha256")):
            continue
        selected.append(fid)
    chosen=set(selected)
    filtered_intake={**intake,"fixtures":[fixtures[id] for id in selected],
                     "fixture_count":len(selected),"research_quote_scope_only":True,
                     "signal_generation_authorized":False}
    filtered_shadow={**shadow,"scored":[scores[id] for id in selected],
                     "scored_count":len(selected),"market_signal_authorized":False,
                     "research_quote_scope_only":True}
    gate={
        "schema":"MATRIX_CHAMPIONSHIP_QUOTE_WINDOW_SCOPE_V1",
        "target_date_bogota":day,
        "checked_at_utc":clock.isoformat(),
        "research_only_eligible_count":len(selected),
        "research_only_ids":selected,
        "status":"PREMATCH_RESEARCH_QUOTE_SCOPE_AVAILABLE" if selected else "NO_VERIFIED_PREMATCH_SCOPE",
        "source_attestation_sha256":digest(attestation),
        "source_intake_sha256":digest(intake),
        "source_shadow_sha256":digest(shadow),
        "never_create_p_matrix":True,
        "production_probability_authorized":False,
        "telegram_signal_authorized":False,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }
    return filtered_intake,filtered_shadow,gate

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",required=True)
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--outdir",type=Path,required=True)
    p.add_argument("--status-out",type=Path,required=True)
    a=p.parse_args()
    folder=a.root/"evidence"/"football_world_inventory"/a.date
    names={
        "intake":"MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
        "shadow":"MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json",
        "attestation":"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json",
        "sofa":"MATRIX_SOFA_FOOTBALL_FIXTURE_CROSSCHECK.json",
        "flash":"MATRIX_FLASH_FOOTBALL_CROSSCHECK.json",
    }
    # Preserve run-scoped PIT attestations rather than overwrite the same
    # daily file in competing Windows/Linux GitHub Action jobs.
    attestation_paths=[
        folder/"MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_ATTESTATION.json",
        *sorted(folder.glob("MATRIX_CHAMPIONSHIP_PROSPECTIVE_PIT_RUN_*.json")),
    ]
    available=[]
    now=datetime.now(timezone.utc)
    for candidate in attestation_paths:
        if not candidate.is_file():
            continue
        try:
            doc=json.loads(candidate.read_text(encoding="utf-8"))
            observed=utc(doc["observed_at_utc"])
            if doc.get("target_date_bogota")==a.date and observed<=now:
                available.append((observed,candidate,doc))
        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
            continue
    selected_attestation=max(available,key=lambda x:(x[0],x[1].name)) if available else None
    missing=[n for n,f in names.items() if n!="attestation" and not (folder/f).is_file()]
    if selected_attestation is None:
        missing.append("attestation")
    eligible=False
    if missing:
        gate={"schema":"MATRIX_CHAMPIONSHIP_QUOTE_WINDOW_SCOPE_V1",
              "target_date_bogota":a.date,"status":"BLOCKED_MISSING_SOURCE_FILES",
              "missing_files":missing,"research_only_eligible_count":0,
              "production_probability_authorized":False,
              "telegram_signal_authorized":False,
              "automatic_wagering":False,"real_money":"BLOCKED"}
    else:
        docs={k:json.loads((folder/f).read_text(encoding="utf-8")) for k,f in names.items() if k!="attestation"}
        docs["attestation"]=selected_attestation[2]
        try:
            x,y,gate=scope(docs["intake"],docs["shadow"],docs["attestation"],
                           docs["sofa"],docs["flash"],now=now)
            gate["source_attestation_file"]=selected_attestation[1].name
            a.outdir.mkdir(parents=True,exist_ok=True)
            (a.outdir/"intake.json").write_text(json.dumps(x,sort_keys=True)+"\n",encoding="utf-8")
            (a.outdir/"shadow.json").write_text(json.dumps(y,sort_keys=True)+"\n",encoding="utf-8")
            eligible=gate["research_only_eligible_count"]>0
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            gate={"schema":"MATRIX_CHAMPIONSHIP_QUOTE_WINDOW_SCOPE_V1",
                  "target_date_bogota":a.date,"status":"BLOCKED_SOURCE_VALIDATION",
                  "reason_type":type(exc).__name__,
                  "research_only_eligible_count":0,
                  "production_probability_authorized":False,
                  "telegram_signal_authorized":False,
                  "automatic_wagering":False,"real_money":"BLOCKED"}
    a.status_out.parent.mkdir(parents=True,exist_ok=True)
    a.status_out.write_text(json.dumps(gate,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as fp:
            fp.write("quote_window="+("true" if eligible else "false")+"\n")
    print(json.dumps({k:gate[k] for k in ("status","research_only_eligible_count",
                                        "telegram_signal_authorized")},sort_keys=True))

if __name__=="__main__":
    main()
