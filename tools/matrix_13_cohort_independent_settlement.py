"""Canonical *parallel*, hash-linked settlement ledger for independently verified FT.

Never modifies the 4958 API-Football hash-chain or pre-match frozen probabilities.
Replays the archived provider response and derives the same strict cross-provider
identity before appending. A conflict or a duplicate never changes prior rows.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime,timezone
from pathlib import Path

from tools.api_football_prospective_api_settlement import _load_ledger as verified_api_ft
from tools.matrix_13_cohort_espn_mls_results import compare as espn_compare
from tools.matrix_13_cohort_independent_results import dt

ROOT=Path(__file__).resolve().parents[1]
FREEZE=ROOT/"evidence/api_football/prospective_market_freeze/freeze.json"
API_LEDGER=ROOT/"evidence/api_football/prospective_market_freeze/settlement_ledger.jsonl"
TRIAGE=ROOT/"evidence/governance/MATRIX_13_COHORT_ARCHIVED_FINAL_READINESS_LAST.json"
SOURCES=ROOT/"evidence/football_cohort_recovery"
LEDGER=ROOT/"evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_LEDGER.jsonl"
OUT=ROOT/"evidence/football_cohort_recovery/MATRIX_INDEPENDENT_VERIFIED_FT_SYNC_LAST.json"


def hash_row(data):
    raw=json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(",",":"),allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _record_hash(item):
    raw=dict(item)
    raw.pop("record_sha256",None)
    return hash_row(raw)


def validated_ledger(path):
    if not path.is_file():
        return []
    rows=[];prev=None;seen=set()
    for n,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
        if not line.strip():
            continue
        row=json.loads(line)
        fid=row.get("fixture_id")
        if not fid or fid in seen or row.get("previous_record_sha256")!=prev or row.get("record_sha256")!=_record_hash(row):
            raise ValueError(f"INDEPENDENT_FT_CHAIN_INVALID:{n}")
        if (row.get("real_money")!="BLOCKED" or row.get("terminal_status")!="FT"
            or row.get("automatic_wagering") is not False
            or row.get("source_provider") not in {"ESPN_MLS","ESPN_CUP"}):
            raise ValueError("INDEPENDENT_FT_SAFETY_OR_SOURCE_INVALID")
        prev=row["record_sha256"];seen.add(fid);rows.append(row)
    return rows


def build_candidates(triage,freeze,source_reports,*,root,api_settled,already):
    if triage.get("target_market_count")!=13:
        raise ValueError("UNTRUSTED_TRIAGE_COUNT")
    freezing={str(row["fixture_id"]):row for row in freeze.get("rows",[])}
    queue={str(row["fixture_id"]):row for row in triage.get("unsettled_fixture_triage",[])}
    if len(queue)!=triage.get("unsettled_fixture_triage_count"):
        raise ValueError("UNTRUSTED_TRIAGE_DUPLICATES")
    old_api={str(x["fixture_id"]) for x in api_settled}
    old_independent={str(x["fixture_id"]):x for x in already}
    candidates=[];rejected=[];seen_new=set()
    for source,report in source_reports:
        if not report:
            continue
        if report.get("real_money")!="BLOCKED" or report.get("canonical_ledger_appends")!=0:
            raise ValueError("UNTRUSTED_PROVIDER_REPORT")
        rows=report.get("matches") if source=="ESPN_MLS" else report.get("matched")
        if not isinstance(rows,list):
            raise ValueError("PROVIDER_REPORT_MATCHES_NOT_LIST")
        for supplied in rows:
            fid=str(supplied.get("api_football_fixture_id") or "")
            tri=queue.get(fid)
            src=freezing.get(fid)
            if not tri or not src or fid in old_api:
                rejected.append({"fixture_id":fid,"reason":"UNKNOWN_OR_ALREADY_CANONICAL_FINAL"})
                continue
            if fid in seen_new:
                raise ValueError("DUPLICATE_INDEPENDENT_PROVIDER_FIXTURE")
            if fid in old_independent:
                if (supplied.get("fulltime_home"),supplied.get("fulltime_away")) != (
                    old_independent[fid]["fulltime_home_goals"],old_independent[fid]["fulltime_away_goals"]):
                    raise ValueError("INDEPENDENT_PRIOR_FINAL_SCORE_CONFLICT")
                continue
            if (tri.get("home_team_name")!=src.get("home_team_name")
                or tri.get("away_team_name")!=src.get("away_team_name")
                or dt(tri["kickoff_utc"])!=dt(src["kickoff_utc"])
                or dt(tri["freeze_at_utc"])!=dt(src["freeze_at_utc"])
                or dt(src["freeze_at_utc"])>=dt(src["kickoff_utc"])):
                raise ValueError("ORIGINAL_PREMATCH_FREEZE_LINEAGE_CONFLICT")
            rel=supplied.get("raw_archive_path")
            if not isinstance(rel,str) or not rel.startswith("evidence/football_cohort_recovery/") or "/" in rel[len("evidence/football_cohort_recovery/"):]:
                raise ValueError("UNTRUSTED_RAW_ARCHIVE_PATH")
            path=root/rel
            if not path.is_file():
                raise ValueError("ORIGINAL_PROVIDER_RESPONSE_MISSING")
            body=path.read_bytes()
            sha=hashlib.sha256(body).hexdigest()
            if sha!=supplied.get("raw_espn_response_sha256"):
                raise ValueError("ORIGINAL_PROVIDER_RESPONSE_HASH_MISMATCH")
            payload=json.loads(body)
            independently_recomputed,unmatched=espn_compare([tri],payload,sha)
            if len(independently_recomputed)!=1 or unmatched:
                raise ValueError("ORIGINAL_PROVIDER_CROSSWALK_FAILED")
            parsed=independently_recomputed[0]
            if (parsed["espn_fixture_id"]!=supplied["espn_fixture_id"]
                or (parsed["fulltime_home"],parsed["fulltime_away"])!=
                    (supplied["fulltime_home"],supplied["fulltime_away"])):
                raise ValueError("PROVIDER_REPORT_VS_RAW_DATA_MISMATCH")
            hg,ag=parsed["fulltime_home"],parsed["fulltime_away"]
            if not isinstance(src.get("input_sha256"),str) or len(src["input_sha256"])!=64:
                raise ValueError("ORIGINAL_FEATURE_SHA_MISSING")
            row={
                "schema":"MATRIX_INDEPENDENT_VERIFIED_STANDARD_FT_V1",
                "fixture_id":fid,
                "target_key":src["target_key"],
                "kickoff_utc":dt(src["kickoff_utc"]).isoformat(),
                "freeze_at_utc":dt(src["freeze_at_utc"]).isoformat(),
                "input_sha256":src["input_sha256"],
                "source_provider":source,
                "source_fixture_id":parsed["espn_fixture_id"],
                "source_raw_sha256":sha,
                "source_raw_path":rel,
                "source_identity_policy":"EXACT_TEAM_PAIR_KICKOFF_WITH_EXPLICIT_MLS_SYNONYMS_V1",
                "terminal_status":"FT",
                "settled_at_utc":datetime.now(timezone.utc).isoformat(),
                "fulltime_home_goals":hg,
                "fulltime_away_goals":ag,
                "halftime_verified":False,
                "outcomes":{"1x2":"H" if hg>ag else "D" if hg==ag else "A",
                            "over_2_5":hg+ag>=3},
                "used_for_market_promotion":False,
                "automatic_wagering":False,
                "real_money":"BLOCKED",
            }
            candidates.append(row);seen_new.add(fid)
    return sorted(candidates,key=lambda x:(x["kickoff_utc"],x["fixture_id"])),rejected


def append(ledger,records):
    existing=validated_ledger(ledger)
    seen={x["fixture_id"] for x in existing}
    for candidate in records:
        if candidate["fixture_id"] in seen:
            raise ValueError("DUPLICATE_INDEPENDENT_SETTLEMENT")
        seen.add(candidate["fixture_id"])
    prev=existing[-1]["record_sha256"] if existing else None
    written=[]
    for raw in records:
        row={**raw,"previous_record_sha256":prev}
        row["record_sha256"]=_record_hash(row)
        prev=row["record_sha256"];written.append(row)
    if written:
        ledger.parent.mkdir(parents=True,exist_ok=True)
        with ledger.open("a",encoding="utf-8") as h:
            for row in written:
                h.write(json.dumps(row,sort_keys=True,ensure_ascii=False)+"\n")
    verified=validated_ledger(ledger)
    if len(verified)!=len(existing)+len(written):
        raise ValueError("APPEND_VERIFY_COUNT_MISMATCH")
    return {"existing":len(existing),"new":len(written),"total":len(verified),
            "append_only":True,"prior_rows_unchanged":True,"canonical_api_football_ledger_unchanged":True}


def main():
    tri=json.loads(TRIAGE.read_text(encoding="utf-8"))
    freeze=json.loads(FREEZE.read_text(encoding="utf-8"))
    base=verified_api_ft(API_LEDGER)
    old=validated_ledger(LEDGER)
    reports=[]
    for k,name in (("ESPN_MLS","MATRIX_ESPN_MLS_EXACT_FINAL_LAST.json"),
                   ("ESPN_CUP","MATRIX_ESPN_CUPS_EXACT_FINAL_LAST.json")):
        p=SOURCES/name
        reports.append((k,json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None))
    rows,blocked=build_candidates(tri,freeze,reports,root=ROOT,api_settled=base,already=old)
    result=append(LEDGER,rows)
    report={
        "schema":"MATRIX_INDEPENDENT_FINAL_APPEND_ONLY_SYNC_V1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PASS_VERIFIED_INDEPENDENT_FT_RESEARCH_ONLY",
        "original_api_football_settled_count":len(base),
        "source_fixture_count":tri.get("unsettled_fixture_triage_count"),
        "verified_independent_ledger":result,
        "rejected":blocked,
        "new_fixture_ids":[r["fixture_id"] for r in rows],
        "no_source_id_substitution":True,
        "no_poststart_prediction_backfill":True,
        "no_parameter_refit":True,
        "no_automatic_promotion":True,
        "telegram_signals_sent":0,
        "automatic_wagering":False,"real_money":"BLOCKED",
    }
    OUT.write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"new":result["new"],
            "cumulative_independent":result["total"],"canonical_original":len(base)},sort_keys=True))


if __name__=="__main__":
    main()
