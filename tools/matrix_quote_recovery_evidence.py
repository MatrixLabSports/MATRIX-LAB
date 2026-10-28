from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[1]
LEDGER=ROOT/"evidence"/"notifications"/"telegram"/"MATRIX_QUOTE_RECOVERY_EXECUTION_LEDGER.jsonl"

def _utc(v:Any)->datetime:
    dt=datetime.fromisoformat(str(v).replace("Z","+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_NOT_AWARE")
    return dt.astimezone(timezone.utc)

def validate(row:dict[str,Any])->dict[str,Any]:
    required=["fixture_id","market","bookmaker","decimal_odds","quote_observed_at_utc","kickoff_utc","p_matrix","revalidated_ev","source_evidence"]
    missing=[k for k in required if row.get(k) in (None,"")]
    if missing: raise ValueError("MISSING_FIELDS:"+",".join(missing))
    if row["market"]!="OVER_2_5": raise ValueError("UNSUPPORTED_CERTIFICATION_MARKET")
    q=float(row["decimal_odds"]); ev=float(row["revalidated_ev"]); p=float(row["p_matrix"])
    if q<=1.50: raise ValueError("ODDS_NOT_STRICTLY_GT_1_50")
    if ev<0.05: raise ValueError("EV_LT_0_05")
    if p<0.60: raise ValueError("P_MATRIX_LT_0_60")
    observed=_utc(row["quote_observed_at_utc"]); kickoff=_utc(row["kickoff_utc"])
    if observed>=kickoff: raise ValueError("QUOTE_NOT_PREMATCH")
    if not str(row["source_evidence"]).strip(): raise ValueError("SOURCE_EVIDENCE_REQUIRED")
    out=dict(row)
    out.update({
      "schema":"MATRIX_QUOTE_RECOVERY_EXECUTION_EVIDENCE_V1",
      "validated":True,
      "automatic_wagering":False,
      "real_money":"BLOCKED"
    })
    raw=json.dumps(out,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    out["record_sha256"]=hashlib.sha256(raw).hexdigest()
    return out

def append(row:dict[str,Any])->dict[str,Any]:
    valid=validate(row)
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    with LEDGER.open("a",encoding="utf-8") as h:
        h.write(json.dumps(valid,sort_keys=True,ensure_ascii=False)+"\n")
    return valid

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--json",required=True)
    a=p.parse_args()
    row=json.loads(Path(a.json).read_text(encoding="utf-8"))
    out=append(row)
    print(json.dumps({"status":"PASS","fixture_id":out["fixture_id"],"record_sha256":out["record_sha256"]},sort_keys=True))

if __name__=="__main__":
    main()
