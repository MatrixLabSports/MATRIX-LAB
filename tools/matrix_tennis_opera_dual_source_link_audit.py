"""Read-only MATRIX tennis calendar link audit from real Opera accessibility captures.

The two providers expose different scopes. This module makes one-to-one
PLAYER NAME LINK REVIEW CANDIDATES, not certified identical fixtures,
UTC kickoff, surface, calibrated probabilities, bookmaker odds or signals.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCHEMA = "MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1"
REVIEW_SCHEMA = "MATRIX_TENNIS_OPERA_DUAL_SOURCE_LINK_REVIEW_V1"
DATE = "2026-11-02"
SOFA_PREFIX = "https://www.sofascore.com/es/tennis/match/"
FLASH_PREFIX = "https://www.flashscore.co/partido/tenis/"
SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
SOFA_DAY = re.compile(r"^2/11/26(?:\s|$)")
ID = re.compile(r"^[0-9]+$")
PLAYER_SEGMENT = re.compile(r"^(.+)-([A-Za-z0-9]{8})$")

def _fold(s: str) -> list[str]:
    s = unicodedata.normalize("NFKD", str(s or "")).casefold()
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", s)

def _url(parsed: str, source: str) -> bool:
    p = urlparse(parsed)
    root = SOFA_PREFIX if source == "SOFASCORE" else FLASH_PREFIX
    return parsed.startswith(root) and p.scheme == "https" and p.hostname == urlparse(root).hostname

def _sofa(event: dict) -> dict | None:
    if not isinstance(event, dict) or not _url(str(event.get("url") or ""), "SOFASCORE"):
        return None
    link = str(event["url"])
    if "#id:" not in link:
        return None
    event_id = link.rsplit("#id:", 1)[-1]
    if not ID.fullmatch(event_id) or str(event.get("source_event_id")) != event_id:
        return None
    p = urlparse(link)
    path = p.path.split("/match/", 1)[-1].split("/")
    if len(path) < 2 or not path[0]:
        return None
    return {"id": event_id, "name":str(event.get("display_name") or ""),
            "url":link, "slug_tokens":set(_fold(path[0]))}

def _flash(event: dict) -> dict | None:
    if not isinstance(event, dict) or not _url(str(event.get("url") or ""), "FLASHSCORE"):
        return None
    link = str(event["url"])
    path = urlparse(link).path.split("/tenis/",1)[-1]
    pieces = [p for p in path.split("/") if p]
    # Doubles or abbreviated fixture links may expose only a match code.
    # They remain observed links, but cannot be linked to named players.
    if len(pieces) != 2:
        return None
    sides = []
    for piece in pieces:
        m = PLAYER_SEGMENT.fullmatch(piece)
        if m is None:
            return None
        tokens = set(_fold(m.group(1)))
        if len(tokens) < 2:
            return None
        sides.append(tokens)
    if sides[0] == sides[1]:
        return None
    # Stable independent player identity, ignoring duplicated preview URLs.
    key = "|".join(sorted(pieces))
    return {"key":key,"name":str(event.get("display_name") or ""),
            "url":link,"player_tokens":sides}

def review(sofa: dict, flash: dict) -> dict:
    if not isinstance(sofa, dict) or not isinstance(flash, dict):
        raise ValueError("INVALID_CAPTURE_OBJECT")
    if sofa.get("schema") != SCHEMA or flash.get("schema") != SCHEMA:
        raise ValueError("UNTRUSTED_LINK_CAPTURE_SCHEMA")
    if sofa.get("source") != "SOFASCORE" or flash.get("source") != "FLASHSCORE":
        raise ValueError("PRIMARY_SOURCE_ORDER_INVALID")
    if sofa.get("target_date_bogota") != DATE or flash.get("target_date_bogota") != DATE:
        raise ValueError("CAPTURE_DATE_MISMATCH")
    for record in (sofa,flash):
        if (record.get("real_money") != "BLOCKED" or
            record.get("telegram_signals_authorized") is not False or
            record.get("automatic_wagering") is not False or
            record.get("canonical_fixture_export_authorized") is not False):
            raise ValueError("CAPTURE_GOVERNANCE_INVALID")
        if record.get("source_order") != SOURCE_ORDER:
            raise ValueError("SOURCE_ORDER_MISMATCH")
        if not isinstance(record.get("matches"),list):
            raise ValueError("MATCH_LINK_ARRAY_REQUIRED")
        if record.get("observed_link_count") != len(record["matches"]):
            raise ValueError("SOURCE_LINK_COUNT_NOT_PHYSICAL")
        urls=[str(x.get("url","")) for x in record["matches"] if isinstance(x,dict)]
        if len(urls)!=len(record["matches"]) or len(urls)!=len(set(urls)):
            raise ValueError("DUPLICATED_SOURCE_URLS")
    dated=[];not_dated=[];sofa_ids=set()
    for x in sofa["matches"]:
        item = _sofa(x)
        if item is None:
            raise ValueError("SOFA_URL_EVENT_ID_INVALID")
        if item["id"] in sofa_ids:
            raise ValueError("DUPLICATED_SOFA_EVENT_ID")
        sofa_ids.add(item["id"])
        if SOFA_DAY.match(item["name"]):
            dated.append(item)
        else:
            not_dated.append({"source_event_id":item["id"],"name":item["name"],"url":item["url"],
                              "reason":"SOFA_TARGET_DATE_NOT_EXPLICIT"})
    flash_links=[]
    unique_flash={}
    for x in flash["matches"]:
        if not _url(str(x.get("url") or ""), "FLASHSCORE"):
            raise ValueError("FLASH_URL_INVALID")
        link=_flash(x)
        if link is None:
            flash_links.append({"name":x.get("display_name"),"url":x["url"],
                                "reason":"NAMED_SINGLE_PLAYER_SLUGS_NOT_BOTH_AVAILABLE"})
            continue
        unique_flash.setdefault(link["key"],link)
    # Candidate identities require both full player-name token sets.
    # No same-day certainty can be inferred from Flashscore's 'mañana' page alone.
    potential=defaultdict(list)
    for key,f in unique_flash.items():
        for s in dated:
            a,b=f["player_tokens"]
            if a <= s["slug_tokens"] and b <= s["slug_tokens"]:
                potential[s["id"]].append(f)
    eligible=[]
    ambiguous=[]
    used_flash=set()
    for s in dated:
        possible=potential.get(s["id"],[])
        if len(possible)!=1:
            if possible:
                ambiguous.append({"sofascore_event_id":s["id"],"reason":"MULTIPLE_FLASH_PLAYER_PAIR_CANDIDATES"})
            continue
        f=possible[0]
        if f["key"] in used_flash:
            ambiguous.append({"sofascore_event_id":s["id"],"reason":"FLASH_PLAYER_PAIR_ALREADY_USED"})
            continue
        used_flash.add(f["key"])
        eligible.append({"sofascore_event_id":s["id"],"sofascore_name":s["name"],
                         "sofascore_url":s["url"],"flashscore_name":f["name"],
                         "flashscore_url":f["url"],
                         "link_identity_basis":"BOTH_FULL_PLAYER_TOKEN_SETS_IN_SOURCE_SLUGS",
                         "same_fixture_certified":False})
    output={
        "schema":REVIEW_SCHEMA,
        "target_date_bogota":DATE,
        "source_order":SOURCE_ORDER,
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "status":"PLAYER_LINK_IDENTITY_CANDIDATES_ONLY_NOT_CERTIFIED_FIXTURES",
        "source_counts":{"sofascore_visible_links":len(sofa["matches"]),
                         "sofascore_explicit_target_date_links":len(dated),
                         "sofascore_without_target_date":len(not_dated),
                         "flashscore_visible_links":len(flash["matches"]),
                         "flashscore_named_player_pair_unique_links":len(unique_flash),
                         "flashscore_unstructured_links":len(flash_links)},
        "candidate_pair_count":len(eligible),
        "ambiguous_pair_count":len(ambiguous),
        "candidate_pairs":eligible,
        "ambiguous_pairs":ambiguous,
        "sofascore_not_explicitly_target_dated":not_dated,
        "flashscore_unstructured_examples":flash_links[:20],
        "provider_page_coverage_complete":False,
        "same_fixture_date_cross_provider_certified":False,
        "utc_kickoff_certified":False,
        "surface_certified":False,
        "model_probability_generation_authorized":False,
        "calibration_parameters_modified":False,
        "bookmaker_quote_verified":False,
        "signal_generation_authorized":False,
        "telegram_messages_sent":0,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    return output

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sofascore",required=True,type=Path)
    p.add_argument("--flashscore",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    result=review(json.loads(a.sofascore.read_text(encoding="utf-8")),
                  json.loads(a.flashscore.read_text(encoding="utf-8")))
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status","source_counts","candidate_pair_count",
                                          "ambiguous_pair_count","signal_generation_authorized")},sort_keys=True))
if __name__=="__main__":
    main()
