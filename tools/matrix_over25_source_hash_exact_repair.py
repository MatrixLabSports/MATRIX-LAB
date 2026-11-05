"""Recover SHA-addressed research source bytes only by exact cryptographic proof.

Some archived JSON snapshots may be pretty-printed after the forecast was
frozen, although the sealed research forecast references their ORIGINAL raw
SHA256. Attempt deterministic whitespace/encoding reconstructions. NEVER use
replacement contents unless SHA256 equals the original frozen commitment.
Original altered bytes are retained under a forensic SHA-named sidecar.
Never touches models, predictions, betting or governed production.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,timezone

ROOT=Path("evidence/football_research_freezes")
MAX_BYTES=24_000_000

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()

def canonical(x:dict)->bytes:
    return (json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")

def variants(obj:dict):
    # Finite encodings from actual Python JSON producer styles, never values.
    for ensure_ascii in (False,True):
        for sort_keys in (True,False):
            for indent in (None,2,4):
                for ending in ("","\n","\r\n"):
                    kw={"ensure_ascii":ensure_ascii,"sort_keys":sort_keys}
                    if indent is None:
                        for separators in ((",",":"),(", ",": ")):
                            raw=(json.dumps(obj,separators=separators,**kw)+ending).encode("utf-8")
                            yield "compact", raw
                            # Windows Git text checkout can change EVERY LF,
                            # not only the last newline. Preserve only bytes
                            # matching the pre-existing frozen SHA256.
                            if b"\n" in raw:
                                yield "compact_all_crlf", raw.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")
                    else:
                        raw=(json.dumps(obj,indent=indent,**kw)+ending).encode("utf-8")
                        yield "pretty", raw
                        if b"\n" in raw:
                            yield "pretty_all_crlf", raw.replace(b"\r\n",b"\n").replace(b"\n",b"\r\n")

def restore(root:Path,*,write:bool=False)->dict:
    path_root=root/ROOT
    errors=[];recovered=[];valid=[];unrecoverable=[]
    for file in sorted(path_root.glob("20??-??-??/sources/[0-9a-f]*.json")):
        expected=file.stem
        if len(expected)!=64 or not all(x in "0123456789abcdef" for x in expected):
            continue
        try:
            if file.stat().st_size>MAX_BYTES:raise ValueError("SOURCE_OVERSIZED")
            current=file.read_bytes()
            current_sha=sha(current)
            if current_sha==expected:
                valid.append(file.relative_to(root).as_posix());continue
            obj=json.loads(current)
            if not isinstance(obj,dict):raise ValueError("SOURCE_NOT_JSON_OBJECT")
            candidates=((kind,data) for kind,data in variants(obj) if sha(data)==expected)
            kind,data=next(candidates,("",None))
            if data is None:
                unrecoverable.append({"path":file.relative_to(root).as_posix(),
                                      "present_sha256":current_sha,
                                      "reason":"ORIGINAL_RAW_BYTES_NOT_RECONSTRUCTIBLE_WITH_VERIFIED_HASH"})
                continue
            forensic=file.parent/"corrupted_originals"/(current_sha+".json")
            if write:
                forensic.parent.mkdir(parents=True,exist_ok=True)
                if forensic.exists():
                    if forensic.read_bytes()!=current:raise ValueError("FORENSIC_BYTES_MISMATCH")
                else:
                    with forensic.open("xb") as f:f.write(current)
                # Same SHA-named path now contains exactly its frozen original
                # commitment, while the altered bytes remain preserved.
                file.write_bytes(data)
                if sha(file.read_bytes())!=expected:raise ValueError("RESTORED_SHA_VERIFICATION_FAILED")
            recovered.append({"path":file.relative_to(root).as_posix(),
                              "altered_bytes_sha256":current_sha,
                              "restored_sha256":expected,
                              "verified_encoding_class":kind,
                              "action":"RESTORED_VERIFIED_RAW_BYTES" if write else "RESTORABLE_NOT_WRITTEN"})
        except (OSError,ValueError,TypeError,json.JSONDecodeError) as exc:
            errors.append({"path":file.relative_to(root).as_posix(),
                           "reason":str(exc)[:140]})
    return {"schema":"MATRIX_OVER25_SOURCE_ARCHIVE_SHA_REPAIR_V1",
            "checked_at_utc":datetime.now(timezone.utc).isoformat(),
            "total_valid_sources":len(valid),
            "verified_sha_restorations":recovered,
            "unrecoverable_sources":unrecoverable,"errors":errors,
            "model_parameters_modified":False,"forecast_bytes_modified":False,
            "telegram_signal_authorized":False,"automatic_wagering":False,
            "real_money":"BLOCKED"}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    parser.add_argument("--restore-verifiable",action="store_true")
    args=parser.parse_args()
    x=restore(args.root,write=args.restore_verifiable)
    out=args.root/"evidence/football_world_inventory/MATRIX_OVER25_RESEARCH_SOURCE_HASH_REPAIR_LAST.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(canonical(x))
    print(json.dumps({"valid":x["total_valid_sources"],
        "verified_restorations":len(x["verified_sha_restorations"]),
        "unrecoverable":len(x["unrecoverable_sources"]),
        "errors":len(x["errors"]),
        "affected_fixtures_never_promoted":True},sort_keys=True))
    if x["errors"]:raise SystemExit("INVALID_ARCHIVE_SOURCE_REPAIR_ERRORS")
if __name__=="__main__":main()
