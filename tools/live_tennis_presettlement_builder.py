from __future__ import annotations
import argparse, hashlib, json, statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def fold_for_match(match_id:int)->int:
    raw=f"matrix-live-tennis-v0.1|match_id={match_id}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:8],16)%5


def first_non_null(rows:list[dict[str,Any]], key:str):
    for r in rows:
        v=r.get(key)
        if v is not None and v!="":
            return v
    return None


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ledger",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    src=Path(args.ledger)
    ledger=json.loads(src.read_text(encoding="utf-8"))
    states=[x for x in ledger.get("states",[]) if isinstance(x,dict)]

    if any(x.get("p1_match_win") is not None or x.get("label_opened") is True for x in states):
        raise SystemExit("LABEL_LEAKAGE_DETECTED_PRESETTLEMENT_BUILD")

    groups=defaultdict(list)
    for row in states:
        mid=row.get("match_id")
        if isinstance(mid,int):
            groups[mid].append(row)

    matches=[]
    missing=Counter()
    domain_counts=Counter()
    state_counts=[]
    for mid in sorted(groups):
        rows=sorted(groups[mid],key=lambda x:(x.get("sequence",-1),x.get("captured_at_utc","")))
        fold=fold_for_match(mid)
        split="HOLDOUT" if fold==4 else "DEVELOPMENT"
        meta={k:first_non_null(rows,k) for k in [
          "tour","gender","surface","tournament","round","round_code",
          "p1_name","p2_name","p1_ranking","p2_ranking"
        ]}
        for k,v in meta.items():
            if v is None:
                missing[k]+=1
        domain=f"{meta['tour'] or 'MISSING'}|{meta['gender'] or 'MISSING'}|{meta['surface'] or 'MISSING'}"
        domain_counts[domain]+=1
        state_counts.append(len(rows))
        matches.append({
          "match_id":mid,
          "fold_5":fold,
          "split":split,
          "domain":domain,
          "metadata":meta,
          "unique_state_count":len(rows),
          "first_sequence":rows[0].get("sequence") if rows else None,
          "last_sequence":rows[-1].get("sequence") if rows else None,
          "first_captured_at_utc":min((x.get("captured_at_utc") for x in rows if x.get("captured_at_utc")),default=None),
          "last_captured_at_utc":max((x.get("captured_at_utc") for x in rows if x.get("captured_at_utc")),default=None),
          "outcome":None,
          "settlement_status":"PENDING_FINAL",
          "metrics_opened":False
        })

    development=[m for m in matches if m["split"]=="DEVELOPMENT"]
    holdout=[m for m in matches if m["split"]=="HOLDOUT"]

    payload={
      "schema":"MATRIX_LIVE_TENNIS_PRESETTLEMENT_DATASET_V0_1",
      "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
      "source_ledger":args.ledger,
      "model_status":"RESEARCH_ONLY",
      "target":"P_LIVE_P1_MATCH_WIN",
      "observation_unit":"UNIQUE_MATCH_SEQUENCE_STATE",
      "grouping_unit":"MATCH_ID",
      "split_policy":{
        "frozen_before_outcomes":True,
        "hash_salt":"matrix-live-tennis-v0.1",
        "folds":5,
        "development_folds":[0,1,2,3],
        "holdout_fold":[4],
        "rule":"SHA256(hash_salt|match_id) mod 5; fold 4 is untouched holdout",
        "no_match_crosses_split":True
      },
      "counts":{
        "unique_matches":len(matches),
        "development_matches":len(development),
        "holdout_matches":len(holdout),
        "unique_states":len(states),
        "states_per_match_min":min(state_counts) if state_counts else 0,
        "states_per_match_median":statistics.median(state_counts) if state_counts else 0,
        "states_per_match_max":max(state_counts) if state_counts else 0
      },
      "domain_match_counts":dict(sorted(domain_counts.items())),
      "metadata_missing_match_counts":dict(sorted(missing.items())),
      "matches":matches,
      "metrics_gate":{
        "opened":False,
        "reason":"NO_FINAL_LABELS_IN_PRESETTLEMENT_DATASET",
        "brier":None,
        "log_loss":None,
        "ece":None,
        "auc":None
      },
      "protections":{
        "outcomes_read":0,
        "labels_present":False,
        "prematch_freeze_mutated":False,
        "odds_to_probability":False,
        "silent_imputation":False,
        "missing_not_zero":True,
        "automatic_wagering":False,
        "real_money":"BLOCKED"
      }
    }

    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
      "status":"PASS",
      "matches":len(matches),
      "development":len(development),
      "holdout":len(holdout),
      "states":len(states),
      "domains":dict(domain_counts),
      "missing":dict(missing)
    },sort_keys=True))

if __name__=="__main__":
    main()
