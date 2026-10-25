"""Read-only post-repair CLV forensic adjudication. No backfill or model changes."""
from __future__ import annotations
import collections
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path("evidence/clv/football/over_2_5")
ATTEMPTS = ROOT / "closing_attempts.jsonl"
LEDGER = ROOT / "prospective_clv_ledger.jsonl"
STATE = ROOT / "state.json"
BASE = "68bff4338b080552836df18c366829a097adff3d"
REPAIR_AT = dt.datetime.fromisoformat("2026-10-23T22:45:32+00:00")
UTC = dt.timezone.utc

def cmd(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True)

def stamp(s: str) -> dt.datetime:
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)

def events(data: str):
    return [json.loads(line) for line in data.splitlines() if line.strip()]

def inventory(items):
    decisions, closings = {}, set()
    for x in items:
        p = x.get("payload") or {}
        if x.get("event_type") == "DECISION_FROZEN":
            decisions[p["decision_id"]] = p
        elif x.get("event_type") == "CLOSING_ODDS_RECORDED":
            closings.add(p["decision_id"])
    return decisions, closings

def short_case(d, attempts):
    ages=[int(a["provider_quote_age_seconds"]) for a in attempts if isinstance(a.get("provider_quote_age_seconds"), (int,float))]
    return {
        "fixture_id":d["fixture_id"],
        "decision_id":d["decision_id"],
        "kickoff_utc":d["fixture_kickoff_utc"],
        "decision_at_utc":d.get("decision_at_utc"),
        "attempts_in_closing_window":len(attempts),
        "outcomes":dict(collections.Counter(a.get("outcome","UNKNOWN") for a in attempts)),
        "max_quote_age_seconds":max(ages) if ages else None,
        "first_attempt_at_utc":min((a.get("attempted_at_utc","") for a in attempts),default=None),
    }

def main():
    now=stamp(json.loads(STATE.read_text())["generated_at_utc"])
    baseline_state=json.loads(cmd("show",f"{BASE}:{STATE}"))
    baseline_events=events(cmd("show",f"{BASE}:{LEDGER}"))
    current_events=events(LEDGER.read_text())
    old_d,old_c=inventory(baseline_events)
    new_d,new_c=inventory(current_events)
    old_missed={k for k,v in old_d.items() if stamp(v["fixture_kickoff_utc"]) <= REPAIR_AT and k not in old_c}
    now_missed={k for k,v in new_d.items() if stamp(v["fixture_kickoff_utc"]) <= now and k not in new_c}
    delta=now_missed-old_missed
    attempt_bytes=ATTEMPTS.read_bytes()
    baseline_bytes=subprocess.check_output(["git","show",f"{BASE}:{ATTEMPTS}"])
    prefix_ok=attempt_bytes.startswith(baseline_bytes)
    rows=events(attempt_bytes.decode("utf-8"))
    post=[r for r in rows if r.get("attempted_at_utc") and stamp(r["attempted_at_utc"])>REPAIR_AT]
    hashes_bad=[]
    for i,r in enumerate(rows,1):
        h=r.get("attempt_sha256")
        if not h: hashes_bad.append(i);continue
        raw={k:v for k,v in r.items() if k!="attempt_sha256"}
        expected=hashlib.sha256(json.dumps(raw,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        if expected!=h: hashes_bad.append(i)
    history=cmd("log",f"--since={REPAIR_AT.isoformat()}","--format=COMMIT:%H:%cI","--numstat","--",str(ATTEMPTS))
    commit_count=0
    deletes=[]
    last_commit=None
    for line in history.splitlines():
        if line.startswith("COMMIT:"):
            commit_count+=1
            last_commit=line[7:]
        elif line.strip() and "\t" in line:
            parts=line.split("\t")
            if len(parts)>=3 and parts[1].isdigit() and int(parts[1])>0:
                deletes.append({"commit":last_commit,"deleted_lines":int(parts[1])})
    by_dec=collections.defaultdict(list)
    for r in post: by_dec[str(r.get("decision_id"))].append(r)
    classified=collections.defaultdict(list)
    attempt_outcomes=collections.Counter(r.get("outcome","UNKNOWN") for r in post)
    stale=["BLOCKED_STALE_PROVIDER_QUOTE","ODDS_API_BLOCKED_STALE_PROVIDER_QUOTE"]
    market=["BLOCKED_MARKET_INCOMPLETE","ODDS_API_BLOCKED_MARKET_INCOMPLETE"]
    provider=["BLOCKED_PROVIDER_ERROR","ODDS_API_BLOCKED_PROVIDER_ERROR","BLOCKED_TEMPORAL","ODDS_API_BLOCKED_TEMPORAL","ODDS_API_BLOCKED_FIXTURE_LOOKUP","ODDS_API_BLOCKED_IDENTITY"]
    valid=["CAPTURED_VALID","ODDS_API_CAPTURED_VALID"]
    for did in sorted(delta,key=lambda k:new_d[k]["fixture_kickoff_utc"]):
        d=new_d[did]
        ko=stamp(d["fixture_kickoff_utc"])
        aa=[a for a in by_dec.get(did,[]) if (ko-dt.timedelta(minutes=15))<=stamp(a["attempted_at_utc"])<ko]
        os={a.get("outcome","UNKNOWN") for a in aa}
        if not aa: cat="scheduler_or_coverage_gap_no_in_window_attempt"
        elif os.issubset(set(stale)):cat="stale_pinnacle_gt120s_only"
        elif os.issubset(set(market)):cat="market_incomplete_only"
        elif os.issubset(set(provider)):cat="provider_error_or_temporal_only"
        else:cat="other_mixed_or_unclassified"
        classified[cat].append(short_case(d,aa))
    order=["stale_pinnacle_gt120s_only","scheduler_or_coverage_gap_no_in_window_attempt","market_incomplete_only","provider_error_or_temporal_only","other_mixed_or_unclassified"]
    stale_ages=[int(r["provider_quote_age_seconds"]) for r in post if r.get("outcome") in stale and isinstance(r.get("provider_quote_age_seconds"),(int,float))]
    valid_ages=[int(r["provider_quote_age_seconds"]) for r in post if r.get("outcome") in valid and isinstance(r.get("provider_quote_age_seconds"),(int,float))]
    fresh_ages=[int(r["provider_quote_age_seconds"]) for r in post if isinstance(r.get("provider_quote_age_seconds"),(int,float)) and 0<=int(r["provider_quote_age_seconds"])<=120]
    dates=collections.Counter(stamp(new_d[k]["fixture_kickoff_utc"]).date().isoformat() for k in delta)
    def outcome_family(s):
        if s in stale: return "stale_gt120"
        if s in market: return "market_incomplete"
        if s=="ODDS_API_BLOCKED_FIXTURE_LOOKUP": return "fixture_lookup"
        if s=="ODDS_API_BLOCKED_IDENTITY": return "identity_mapping"
        if s in ("BLOCKED_PROVIDER_ERROR","ODDS_API_BLOCKED_PROVIDER_ERROR"): return "provider_error"
        if s in ("BLOCKED_TEMPORAL","ODDS_API_BLOCKED_TEMPORAL"): return "temporal"
        if s in valid: return "captured_valid"
        return "other"
    signatures=collections.Counter()
    family_cases=collections.Counter()
    signature_samples={}
    for cat in order:
        for case in classified[cat]:
            families=tuple(sorted({outcome_family(s) for s in case["outcomes"]}))
            signature="+".join(families) if families else "no_attempt"
            signatures[signature]+=1
            signature_samples.setdefault(signature,case)
            for fam in families: family_cases[fam]+=1
    signature_examples={k:{"fixture_id":v["fixture_id"],"kickoff_utc":v["kickoff_utc"],"outcomes":v["outcomes"],"max_quote_age_seconds":v["max_quote_age_seconds"]} for k,v in signature_samples.items()}
    report={
        "schema":"MATRIX_CLV_POST23_FORENSIC_READ_ONLY_V1",
        "repair_baseline_commit":BASE,
        "repair_baseline_utc":REPAIR_AT.isoformat(),
        "current_state_generated_at_utc":now.isoformat(),
        "baseline_missed_state":baseline_state["closing_cycle"]["missed_after_kickoff"],
        "current_missed_state":json.loads(STATE.read_text())["closing_cycle"]["missed_after_kickoff"],
        "state_missed_delta":json.loads(STATE.read_text())["closing_cycle"]["missed_after_kickoff"]-baseline_state["closing_cycle"]["missed_after_kickoff"],
        "reconciled_new_missed_decisions":len(delta),
        "baseline_missed_decisions_reconstructed":len(old_missed),
        "current_missed_decisions_reconstructed":len(now_missed),
        "new_missed_by_kickoff_utc_date":dict(sorted(dates.items())),
        "categories_mutually_exclusive":{cat:len(classified[cat]) for cat in order},
        "misses_with_evidence_by_cause_nonexclusive":dict(sorted(family_cases.items())),
        "mutually_exclusive_cause_combinations":dict(sorted(signatures.items())),
        "cause_combination_examples":signature_examples,
        "case_samples":{cat:classified[cat][:4] for cat in order},
        "all_cases_compact":[{"category":cat,**x} for cat in order for x in classified[cat]],
        "post_repair_attempt_rows":len(post),
        "post_repair_attempt_outcomes":dict(sorted(attempt_outcomes.items())),
        "maximum_quote_age_valid_capture_seconds":max(valid_ages) if valid_ages else None,
        "maximum_quote_age_stale_blocked_seconds":max(stale_ages) if stale_ages else None,
        "maximum_quote_age_fresh_observed_seconds":max(fresh_ages) if fresh_ages else None,
        "attempts_total_lines":len(rows),
        "attempts_post_repair_by_utc_date":dict(sorted(collections.Counter(stamp(x["attempted_at_utc"]).date().isoformat() for x in post).items())),
        "append_only":{
            "baseline_blob_prefix_of_current":prefix_ok,
            "baseline_bytes":len(baseline_bytes),
            "current_bytes":len(attempt_bytes),
            "commits_touching_attempt_log_since_repair":commit_count,
            "commits_with_deleted_lines":deletes[:12],
            "commits_with_deleted_lines_count":len(deletes),
            "attempt_hash_invalid_rows_count":len(hashes_bad),
            "attempt_hash_invalid_rows_sample":hashes_bad[:10],
            "verified":prefix_ok and not deletes and not hashes_bad
        },
        "freshness_gate_seconds":120,
        "push_transport_recommendation":"NO_MIGRATION_UNTIL_RECENT_CAUSES_ADJUDICATED_AND_TRIAL_GATE_MET",
        "real_money":"BLOCKED"
    }
    Path("/tmp/MATRIX_CLV_POST23_FORENSIC_25OCT2026.json").write_text(json.dumps(report,ensure_ascii=False,sort_keys=True,indent=2)+"\\n",encoding="utf-8")
    print("MATRIX_CLV_FORENSIC_JSON="+json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(",",":")))
    assert len(delta)==report["state_missed_delta"], "MISMATCH_MISSED_DELTA"
    assert sum(report["categories_mutually_exclusive"].values())==len(delta)
    assert report["append_only"]["verified"], "ATTEMPT_LOG_NOT_PROVEN_APPEND_ONLY"
    print("MATRIX_CLV_FORENSIC_RECONCILIATION=PASS")
if __name__=="__main__":
    main()
