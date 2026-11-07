from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

UTR_RE=re.compile(r"^UTR\s+PTT\s+.*\b(Men|Women)\b",re.I)

def lane(row):
    return "|".join([
        str(row.get("tour") or "unknown").lower(),
        str(row.get("gender") or "unknown").lower(),
        str(row.get("surface") or "unknown").lower(),
    ])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    lp=Path(args.ledger)
    j=json.loads(lp.read_text(encoding="utf-8"))
    states=[x for x in j.get("states",[]) if isinstance(x,dict)]
    before=Counter(lane(x) for x in states)
    changed=0
    match_ids=set()

    for row in states:
        tournament=str(row.get("tournament") or "").strip()
        m=UTR_RE.search(tournament)
        if not m:
            continue
        updates={}
        if not row.get("tour"):
            updates["tour"]="utr"
        if not row.get("gender"):
            updates["gender"]="men" if m.group(1).lower()=="men" else "women"
        if not updates:
            continue
        row.setdefault("metadata_reconciliation",{})
        row["metadata_reconciliation"].update({
            "rule":"EXPLICIT_UTR_PTT_TOURNAMENT_LABEL",
            "source_field":"tournament",
            "source_value":tournament,
            "reconciled_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "surface_imputed":False
        })
        row.update(updates)
        changed+=1
        if isinstance(row.get("match_id"),int):
            match_ids.add(row["match_id"])

    after=Counter(lane(x) for x in states)
    lp.write_text(json.dumps(j,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")

    evidence={
      "schema":"MATRIX_LIVE_TENNIS_METADATA_RECONCILIATION_V0_1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "source_ledger":args.ledger,
      "rule":"Only explicit tournament labels matching UTR PTT ... Men/Women may fill missing tour/gender.",
      "states_changed":changed,
      "matches_changed":len(match_ids),
      "before_lane_counts":dict(sorted(before.items())),
      "after_lane_counts":dict(sorted(after.items())),
      "surface_imputations":0,
      "protections":{
        "silent_imputation":False,
        "missing_surface_preserved":True,
        "labels_mutated":False,
        "real_money":"BLOCKED"
      }
    }
    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(evidence,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":"PASS","states_changed":changed,"matches_changed":len(match_ids),"after_lane_counts":evidence["after_lane_counts"]},sort_keys=True))

if __name__=="__main__":
    main()
