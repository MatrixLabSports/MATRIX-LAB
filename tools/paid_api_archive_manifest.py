from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ROOTS = [
    "evidence/tennis_world_inventory",
    "evidence/tennis/world_inventory",
    "evidence/cor0203/acquisition",
    "evidence/cor0203/api_tennis_stats_rich",
    "evidence/cor0203/rapidapi_stats_rich",
    "evidence/cor0203/preholdout",
    "evidence/api_football/history",
    "evidence/api_football/fixtures",
    "evidence/api_football/prospective_daily",
    "evidence/api_football/market_expansion",
    "evidence/live_tennis_lab",
]

def file_sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def root_manifest(root: Path) -> dict[str, Any]:
    rows=[]
    if not root.exists():
        return {
            "root": str(root),
            "exists": False,
            "file_count": 0,
            "total_bytes": 0,
            "tree_sha256": None,
            "files": [],
        }
    for p in sorted(x for x in root.rglob("*") if x.is_file()):
        rel=p.relative_to(root).as_posix()
        rows.append({
            "path": rel,
            "bytes": p.stat().st_size,
            "sha256": file_sha(p),
        })
    h=hashlib.sha256()
    for row in rows:
        h.update(row["path"].encode("utf-8")); h.update(b"\0")
        h.update(row["sha256"].encode("ascii")); h.update(b"\0")
        h.update(str(row["bytes"]).encode("ascii")); h.update(b"\n")
    return {
        "root": str(root),
        "exists": True,
        "file_count": len(rows),
        "total_bytes": sum(x["bytes"] for x in rows),
        "tree_sha256": h.hexdigest(),
        "files": rows,
    }

def build(roots: list[str], out: Path) -> dict[str, Any]:
    manifests=[root_manifest(Path(x)) for x in roots]
    payload={
        "schema":"MATRIX_PAID_API_PRESERVATION_MANIFEST_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "purpose":"Permanently inventory paid-source evidence before subscription expiry. No secrets are stored.",
        "roots":manifests,
        "summary":{
            "root_count":len(manifests),
            "existing_root_count":sum(1 for x in manifests if x["exists"]),
            "file_count":sum(x["file_count"] for x in manifests),
            "total_bytes":sum(x["total_bytes"] for x in manifests),
        },
        "providers_covered":[
            "rapidapi_tennis",
            "api_tennis",
            "api_football",
            "live_tennis_api"
        ],
        "protections":{
            "secrets_persisted":False,
            "metrics_opened":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED"
        }
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    payload["sha256_without_self"]=hashlib.sha256(raw).hexdigest()
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return payload

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",action="append",dest="roots")
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=build(a.roots or DEFAULT_ROOTS,Path(a.out))
    print(json.dumps({
        "status":"PASS",
        **result["summary"],
        "sha256_without_self":result["sha256_without_self"],
        "real_money":"BLOCKED"
    },sort_keys=True))

if __name__=="__main__":
    main()
