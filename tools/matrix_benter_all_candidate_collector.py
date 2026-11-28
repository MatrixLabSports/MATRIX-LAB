from __future__ import annotations
import hashlib,json,statistics
from pathlib import Path
from typing import Any,Mapping

DATE="2026-10-16"
REPORT=Path(f"evidence/api_football/daily_prematch_reports/{DATE}/over25_shadow_ev/MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV.json")
RAW=REPORT.parent/"raw"
OUT=Path(f"evidence/api_football/model_validation/benter_second_stage/{DATE}/MATRIX_BENTER_ALL_CANDIDATE_MARKET_SNAPSHOT_V1.json")
MIN_BOOKS_FOR_CONSENSUS=2

def _sha(x:Any)->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()

def _file_sha(p:Path)->str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def _pair(od_over:float,od_under:float)->dict[str,float]:
    io,iu=1.0/od_over,1.0/od_under
    z=io+iu
    return {"over":io/z,"under":iu/z,"overround":z}

def extract_books(payload:Mapping[str,Any])->list[dict[str,Any]]:
    out=[]
    for fr in payload.get("response") or []:
        if not isinstance(fr,Mapping): continue
        update=fr.get("update")
        for bm in fr.get("bookmakers") or []:
            if not isinstance(bm,Mapping): continue
            over=under=None
            for bet in bm.get("bets") or []:
                if not isinstance(bet,Mapping): continue
                try: bid=int(bet.get("id"))
                except Exception: continue
                if bid!=5 or str(bet.get("name") or "").strip().casefold()!="goals over/under": continue
                for v in bet.get("values") or []:
                    if not isinstance(v,Mapping): continue
                    label=str(v.get("value") or "").strip().casefold()
                    try: odd=float(v.get("odd"))
                    except Exception: continue
                    if odd<=1.0: continue
                    if label=="over 2.5": over=odd
                    elif label=="under 2.5": under=odd
            if over is None or under is None: continue
            d=_pair(over,under)
            out.append({
                "bookmaker_id":bm.get("id"),"bookmaker_name":bm.get("name"),
                "over_odds":over,"under_odds":under,
                "overround":d["overround"],
                "devig_over_probability":d["over"],
                "devig_under_probability":d["under"],
                "provider_quote_updated_at_utc":update,
            })
    return out

def build(report:Mapping[str,Any], raw_root:Path=RAW)->dict[str,Any]:
    rows=[]
    for r in report.get("all_rows") or []:
        if not isinstance(r,Mapping) or r.get("p_over_2_5") is None: continue
        fid=str(r.get("fixture_id") or "")
        path=raw_root/f"fixture_{fid}.bin"
        books=[]
        raw_sha=None
        if path.is_file():
            raw_sha=_file_sha(path)
            try:
                payload=json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload,Mapping): books=extract_books(payload)
            except Exception:
                books=[]
        ps=[float(x["devig_over_probability"]) for x in books]
        consensus=statistics.median(ps) if len(ps)>=MIN_BOOKS_FOR_CONSENSUS else None
        spread=(max(ps)-min(ps)) if len(ps)>=2 else None
        rows.append({
            "fixture_id":fid,"match":r.get("match"),"kickoff_utc":r.get("kickoff_utc"),
            "model_probability":float(r["p_over_2_5"]),
            "market_probability_devigged_consensus":consensus,
            "market_consensus_method":"MEDIAN_SAME_MARKET_BOOK_DEVIGGED_OVER25" if consensus is not None else None,
            "valid_book_pair_count":len(books),
            "market_probability_range":spread,
            "book_pairs":books,
            "outcome_over25":None,
            "outcome_status":"PENDING_FINAL_OUTCOME",
            "raw_odds_payload_sha256":raw_sha,
        })
    priced=sum(x["market_probability_devigged_consensus"] is not None for x in rows)
    out={
        "schema":"MATRIX_BENTER_ALL_CANDIDATE_MARKET_SNAPSHOT_V1",
        "target_date_bogota":DATE,
        "row_count":len(rows),
        "devigged_consensus_count":priced,
        "missing_consensus_count":len(rows)-priced,
        "minimum_books_for_consensus":MIN_BOOKS_FOR_CONSENSUS,
        "rows":rows,
        "source_report":REPORT.as_posix(),
        "source_report_sha256":_file_sha(REPORT) if REPORT.exists() else None,
        "governance":{
            "research_only":True,
            "all_scored_candidates_not_signal_selected_only":True,
            "market_probability_is_post_model":True,
            "production_p_matrix_modified":False,
            "market_probability_fused_into_production":False,
            "outcome_backfill_before_snapshot":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        }
    }
    out["artifact_sha256"]=_sha({k:v for k,v in out.items() if k!="artifact_sha256"})
    return out

def main():
    report=json.loads(REPORT.read_text(encoding="utf-8"))
    out=build(report)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","row_count":out["row_count"],"devigged_consensus_count":out["devigged_consensus_count"],"artifact_sha256":out["artifact_sha256"],"real_money":out["governance"]["real_money"]},sort_keys=True))

if __name__=="__main__": main()
