from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

MAX_CHUNK_BYTES = 1_500_000


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))+"\n").encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def write_chunked_json(*, payload: Any, out_dir: Path, base_name: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir = out_dir / (base_name + "_chunks")
    chunks_dir.mkdir(parents=True, exist_ok=True)

    if isinstance(payload, list):
        root_kind = "list"
        list_key = None
        rows = payload
        metadata = None
    elif isinstance(payload, dict):
        list_candidates=[(k,v) for k,v in payload.items() if isinstance(v,list)]
        if not list_candidates:
            raise ValueError("CHUNKABLE_LIST_FIELD_REQUIRED")
        list_key, rows=max(list_candidates,key=lambda kv: len(_canonical_bytes(kv[1])))
        root_kind="dict_with_chunked_list"
        metadata={k:v for k,v in payload.items() if k!=list_key}
    else:
        raise ValueError("CHUNKABLE_JSON_ROOT_REQUIRED")

    for old in chunks_dir.glob("chunk_*.json"):
        old.unlink()

    chunks=[]
    current=[]
    current_size=2
    index=1
    for row in rows:
        raw=_canonical_bytes(row)
        if len(raw) > MAX_CHUNK_BYTES:
            raise ValueError("SINGLE_ROW_EXCEEDS_CHUNK_LIMIT")
        if current and current_size + len(raw) + 2 > MAX_CHUNK_BYTES:
            path=chunks_dir/f"chunk_{index:04d}.json"
            body=(json.dumps(current,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
            path.write_bytes(body)
            chunks.append({"path":path.as_posix(),"sha256":_sha(body),"rows":len(current),"bytes":len(body)})
            index+=1
            current=[]
            current_size=2
        current.append(row)
        current_size += len(raw)+1
    if current:
        path=chunks_dir/f"chunk_{index:04d}.json"
        body=(json.dumps(current,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
        path.write_bytes(body)
        chunks.append({"path":path.as_posix(),"sha256":_sha(body),"rows":len(current),"bytes":len(body)})

    manifest={
        "schema":"MATRIX_CHUNKED_JSON_STORE_V1",
        "base_name":base_name,
        "root_kind":root_kind,
        "chunked_list_key":list_key,
        "metadata":metadata,
        "row_count":len(rows),
        "chunk_count":len(chunks),
        "max_chunk_bytes":MAX_CHUNK_BYTES,
        "chunks":chunks,
    }
    manifest_raw=_canonical_bytes(manifest)
    manifest["manifest_sha256_without_self"]=_sha(manifest_raw)
    manifest_path=out_dir/(base_name+"_manifest.json")
    manifest_path.write_text(json.dumps(manifest,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    return manifest


def load_chunked_json(manifest_path: Path) -> Any:
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    rows=[]
    for item in manifest["chunks"]:
        path=Path(item["path"])
        raw=path.read_bytes()
        if _sha(raw)!=item["sha256"]:
            raise ValueError("CHUNK_SHA256_MISMATCH:"+path.as_posix())
        part=json.loads(raw.decode("utf-8"))
        if not isinstance(part,list) or len(part)!=int(item["rows"]):
            raise ValueError("CHUNK_ROW_COUNT_MISMATCH:"+path.as_posix())
        rows.extend(part)
    if len(rows)!=int(manifest["row_count"]):
        raise ValueError("TOTAL_ROW_COUNT_MISMATCH")
    if manifest["root_kind"]=="list":
        return rows
    if manifest["root_kind"]=="dict_with_chunked_list":
        out=dict(manifest.get("metadata") or {})
        out[str(manifest["chunked_list_key"])]=rows
        return out
    raise ValueError("UNKNOWN_CHUNKED_ROOT_KIND")
