from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _sha_without_self(payload: dict[str, Any]) -> str:
    base=dict(payload)
    base.pop("sha256_without_self",None)
    raw=json.dumps(base,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


def sync(parent: dict[str,Any], prospective: dict[str,Any]) -> dict[str,Any]:
    if parent.get("lane_id")!=prospective.get("lane_id"):
        raise ValueError("LANE_ID_MISMATCH")
    if parent.get("holdout_id")!=prospective.get("holdout_id"):
        raise ValueError("HOLDOUT_ID_MISMATCH")
    if prospective.get("real_money")!="BLOCKED":
        raise ValueError("PROSPECTIVE_REAL_MONEY_NOT_BLOCKED")
    if prospective.get("metrics_opened") is not False:
        raise ValueError("PROSPECTIVE_METRICS_OPENED")
    if int(prospective.get("outcomes_read") or 0)!=0:
        raise ValueError("PROSPECTIVE_OUTCOMES_READ")

    out=dict(parent)
    count=int(prospective.get("observation_count") or 0)
    out["prospective_observations"]=count
    out["holdout_status"]="ACTIVE_PROSPECTIVE" if count>0 else "ACTIVE_ZERO_OBSERVATIONS"
    out["metrics_opened"]=False
    out["real_money"]="BLOCKED"
    out["status"]="ACTIVE_PROSPECTIVE_RESEARCH"
    out["prospective_state_status"]=prospective.get("status")
    out["prospective_unique_physical_event_count"]=int(prospective.get("unique_physical_event_count") or 0)
    out["sha256_without_self"]=_sha_without_self(out)
    return out


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--parent",required=True)
    p.add_argument("--prospective",required=True)
    p.add_argument("--out")
    a=p.parse_args()
    parent_path=Path(a.parent)
    prospective_path=Path(a.prospective)
    parent=json.loads(parent_path.read_text(encoding="utf-8"))
    prospective=json.loads(prospective_path.read_text(encoding="utf-8"))
    out=sync(parent,prospective)
    out_path=Path(a.out) if a.out else parent_path
    out_path.write_text(json.dumps(out,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "lane_id":out["lane_id"],
        "prospective_observations":out["prospective_observations"],
        "holdout_status":out["holdout_status"],
        "metrics_opened":out["metrics_opened"],
        "real_money":out["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
