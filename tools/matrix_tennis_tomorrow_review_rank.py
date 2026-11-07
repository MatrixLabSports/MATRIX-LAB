"""Rank saved tennis calendar candidates without authorizing events.

A complete surname overlap is a strong review lead, NOT event certification.
"""
from __future__ import annotations
import json
from pathlib import Path

INPUT = Path(__file__).resolve().parents[1] / "evidence/calendar/MATRIX_TENNIS_TOMORROW_REVIEW_20261031.json"

def classify(data: dict) -> dict:
    if data.get("review_only") is not True or data.get("certified") != 0 or data.get("signals_authorized") != 0:
        raise ValueError("Only uncertified review evidence is accepted")
    out = []
    for row in data["candidates"]:
        opts = row.get("candidates", [])
        if not opts:
            raise ValueError("Candidate row without alternatives")
        max_shared = max(o["shared_token_count"] for o in opts)
        best = [o for o in opts if o["shared_token_count"] == max_shared]
        out.append({"sofascore_url":row["sofascore_url"],
                    "sofascore_name":row["sofascore_name"],
                    "best_shared_token_count":max_shared,
                    "best_options":best,
                    "multiple_original_options":len(opts)>1,
                    "ambiguous_best_score":len(best)>1,
                    "status":"REVIEW_ONLY",
                    "requires":"Verify both sides, event date, tournament and event IDs on both sources",
                    "certified":False,"signals_authorized":False})
    return {"target_date":data["target_date"],"candidate_events":len(out),
            "with_multiple_options":sum(r["multiple_original_options"] for r in out),
            "ambiguous_best_score":sum(r["ambiguous_best_score"] for r in out),
            "certified":0,"signals_authorized":0,"records":out}

def main() -> None:
    data=json.loads(INPUT.read_text(encoding="utf-8"))
    report=classify(data)
    print(json.dumps({k:v for k,v in report.items() if k!="records"},indent=2))

if __name__=="__main__":
    main()
