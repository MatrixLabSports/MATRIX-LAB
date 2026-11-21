"""Exact browser-first tennis cross-source match-name hints.

Never count a source-name match as a certified fixture or a model observation.
Match on *the complete normalized unordered name-token multiset*; names that
do not align exactly, duplicated fixtures, missing provider ID or malformed
URLs are refused without fuzzy matching, guessing a surface or start time.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from tools.matrix_tennis_browser_first_free_intake import get,ROOT

OUT=Path("evidence/tennis_calendar_reconciliation")
INPUTS={"SOFASCORE":"sofascore_opera_full_link_observations.json",
        "FLASHSCORE":"flashscore_opera_full_link_observations.json"}

def fingerprint(value):
    ascii_value=unicodedata.normalize("NFKD",value).encode("ascii","ignore").decode("ascii")
    return tuple(sorted(x for x in re.split(r"[^a-z0-9]+",ascii_value.casefold()) if x))

def identity(source,row):
    url=row.get("url")
    if not isinstance(url,str):return None
    u=urlparse(url)
    if u.scheme!="https" or u.username or u.password:return None
    chunks=[x for x in u.path.split("/") if x]
    if source=="SOFASCORE":
        if u.hostname not in ("sofascore.com","www.sofascore.com") or len(chunks)!=5 or chunks[:3]!=["es","tennis","match"]:
            return None
        ids=parse_qs(u.fragment.replace("id:","id=")).get("id",[])
        if len(ids)!=1 or not ids[0].isdigit():return None
        name=chunks[3];mid=ids[0]
    else:
        if u.hostname not in ("flashscore.co","www.flashscore.co") or len(chunks)!=4 or chunks[:2]!=["partido","tenis"]:
            return None
        a,b=chunks[2],chunks[3]
        if "-" not in a or "-" not in b:return None
        # Last dash component is stable player slug-ID in Flashscore.
        p1,s1=a.rsplit("-",1);p2,s2=b.rsplit("-",1)
        if not (s1.isalnum() and s2.isalnum() and len(s1)>=5 and len(s2)>=5):
            return None
        name=p1+"-"+p2
        mids=parse_qs(u.query).get("mid",[])
        mid=mids[0] if len(mids)==1 and mids[0].isalnum() else None
        if mid is None:return None
    tokens=fingerprint(name)
    if len(tokens)<4 or len(set(tokens))<3:return None
    return {"id":mid,"name_tokens":tokens,"url":url}

def reconcile(root:Path,day:str):
    date.fromisoformat(day)
    grouped={}
    captures={}
    for source,filename in INPUTS.items():
        doc,h=get(root,ROOT/day/filename)
        if doc is None:
            return {"schema":"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1",
                    "target_date_bogota":day,
                    "status":"REQUIRED_SOURCE_NOT_CAPTURED",
                    "matched_exact_name_hints":0,
                    "matches":[],"sources_available":list(captures),
                    "hard_holdout_admitted":0,"clay_holdout_admitted":0,
                    "telegram_signal_authorized":False,"real_money":"BLOCKED"}
        if (doc.get("schema")!="MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1" or
            doc.get("source")!=source or doc.get("target_date_bogota")!=day or
            doc.get("real_money")!="BLOCKED" or
            doc.get("canonical_fixture_export_authorized") is not False or
            doc.get("probability_generation_authorized") is not False):
            raise ValueError("UNTRUSTED_SOURCE_"+source)
        g=defaultdict(list)
        for row in doc.get("matches") or []:
            if not isinstance(row,dict):continue
            native=identity(source,row)
            if native:g[native["name_tokens"]].append(native)
        grouped[source]=g
        captures[source]=h
    pairs=[]
    for tokens in sorted(set(grouped["SOFASCORE"])&set(grouped["FLASHSCORE"])):
        sof=grouped["SOFASCORE"][tokens]
        fla=grouped["FLASHSCORE"][tokens]
        # Links for a single fixture sometimes repeat in the accessibility
        # tree. Collapse exact URL but reject multiple distinct identities.
        sof={x["id"]:x for x in sof}
        fla={x["id"]:x for x in fla}
        if len(sof)!=1 or len(fla)!=1:continue
        a=next(iter(sof.values()));b=next(iter(fla.values()))
        pairs.append({"source_name_token_key":" ".join(tokens),
                      "sofascore_id":a["id"],"flashscore_mid":b["id"],
                      "sofascore_url":a["url"],"flashscore_url":b["url"],
                      "matching_authority":"EXACT_NORMALIZED_UNORDERED_NAME_TOKENS_ONLY",
                      "same_event_verified":False,
                      "same_day_per_event_verified":False,
                      "tournament_verified":False,"surface_verified":False,
                      "start_utc_verified":False,"historic_pit_verified":False,
                      "hard_holdout_admitted":False,"clay_holdout_admitted":False})
    return {"schema":"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1",
      "target_date_bogota":day,
      "status":"RESEARCH_IDENTITY_HINTS_ONLY_NO_EVENT_EQUIVALENCE",
      "source_capture_sha256":captures,
      "matched_exact_name_hints":len(pairs),
      "matches":pairs,"hard_holdout_admitted":0,"clay_holdout_admitted":0,
      "model_calibration_mutated":False,
      "source_event_equivalence_certified":False,
      "telegram_signal_authorized":False,"automatic_wagering":False,
      "real_money":"BLOCKED"}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path.cwd())
    p.add_argument("--date",required=True)
    args=p.parse_args()
    value=reconcile(args.root,args.date)
    output=args.root/OUT/args.date/"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json"
    output.parent.mkdir(parents=True,exist_ok=True)
    new_bytes=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+"\n").encode("utf-8")
    if output.exists():
        old_bytes=output.read_bytes()
        if old_bytes != new_bytes:
            # Preserve the EXACT research snapshot to which individual
            # prematch details were cryptographically bound. The archive
            # never grants identity or model admission and cannot overwrite
            # a different payload with the same digest.
            old=json.loads(old_bytes)
            if (old.get("schema")!="MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1"
                or old.get("target_date_bogota")!=args.date
                or old.get("real_money")!="BLOCKED"
                or old.get("source_event_equivalence_certified") is not False):
                raise ValueError("CROSSMATCH_ARCHIVE_OLD_GOVERNANCE_INVALID")
            digest=hashlib.sha256(old_bytes).hexdigest()
            archive=output.parent/"archive"/(
                "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_"+digest+".json")
            archive.parent.mkdir(parents=True,exist_ok=True)
            if archive.exists():
                if archive.read_bytes()!=old_bytes:
                    raise ValueError("CROSSMATCH_ARCHIVE_SHA256_COLLISION_OR_TAMPER")
            else:
                archive.write_bytes(old_bytes)
                if archive.read_bytes()!=old_bytes:
                    raise ValueError("CROSSMATCH_ARCHIVE_WRITE_VERIFICATION_FAILED")
    output.write_bytes(new_bytes)
    print(json.dumps({"exact_name_hints":value["matched_exact_name_hints"],
                     "hard_admitted":0,"clay_admitted":0,
                     "status":value["status"]},sort_keys=True))

if __name__=="__main__":main()
