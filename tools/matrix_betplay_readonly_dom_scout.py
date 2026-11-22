"""Read-only BetPlay full-time Over 2.5 quote scout; NEVER a signal producer.

An exact visible label is a physical DOM observation, not an executable
bookmaker event ID, official P_MATRIX, sharp quote, or green signal.
No clicks, logins, account reads, cookies, hidden API calls or bet placement.
"""
from __future__ import annotations
import hashlib,json,math,re
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse

SCHEMA="MATRIX_BETPLAY_READONLY_DOM_RESEARCH_MARKET_V1"
PATTERN=re.compile(
    r"^Apuesta sobre (?P<home>[^\\n]+?) vs (?P<away>[^\\n]+?)"
    r" - Total de goles - Más de 2[.,]5 en (?P<odds>[0-9]{1,3}[.,][0-9]{1,3})$"
)


def parse_labels(labels:list[str],source_url:str,at:datetime)->dict:
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("QUOTE_CAPTURE_REQUIRES_REAL_UTC")
    at=at.astimezone(timezone.utc)
    site=urlparse(source_url)
    if site.scheme!="https" or site.hostname not in {"betplay.com.co","www.betplay.com.co"}:
        raise ValueError("QUOTE_SITE_MUST_BE_AUTHORIZED_BETPLAY_DOMAIN")
    if not isinstance(labels,list) or len(labels)>600:
        raise ValueError("VISIBLE_BUTTON_LABELS_INVALID")
    found={};duplicates=set()
    for label in labels:
        if not isinstance(label,str) or len(label)>260:
            continue
        m=PATTERN.fullmatch(label.strip())
        if m is None:
            continue
        home,away=m.group("home").strip(),m.group("away").strip()
        odds=float(m.group("odds").replace(",","."))
        if (not home or not away or home.casefold()==away.casefold()
            or not math.isfinite(odds) or not 1.50<odds<=50):
            continue
        key=(home.casefold(),away.casefold(),"OVER_2_5")
        if key in found:
            duplicates.add(key)
        found[key]={"bookmaker":"BetPlay","home_label":home,"away_label":away,
                    "market":"Total de goles","selection":"Más de 2.5",
                    "decimal_price":odds,"raw_visible_accessibility_label":label,
                    "bookmaker_event_id":None,"event_kickoff_utc":None,
                    "original_api_football_fixture_id":None,
                    "official_p_matrix":None,"verified_sharp_120s":False,
                    "research_only":True,"telegram_signal_authorized":False}
    # Disallow choosing a favorable one of multiple visible prices for a match.
    for key in duplicates:
        found.pop(key,None)
    rows=sorted(found.values(),key=lambda r:(r["home_label"],r["away_label"]))
    sha=hashlib.sha256(
        json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
    ).hexdigest()
    return {"schema":SCHEMA,
            "status":"RESEARCH_VISIBLE_QUOTE_LABELS_NO_MODEL_NO_EVENT_ID",
            "observed_at_utc":at.isoformat(),"source_url":source_url,
            "source":"VISIBLE_RENDERED_BETPLAY_ACCESSIBLE_BUTTON_LABELS",
            "read_only":True,"exact_visible_over25_quote_count":len(rows),
            "ambiguous_duplicate_event_labels_rejected":len(duplicates),
            "quote_labels_sha256":sha,"quotes":rows,
            "calendar_first_preference":["SOFASCORE","FLASHSCORE"],
            "requires_independent_exact_event_kickoff_and_provider_crosswalk":True,
            "requires_price_revalidation_in_final_120m":True,
            "production_p_matrix_authorized":False,
            "telegram_signal_authorized":False,
            "automatic_wagering":False,"real_money":"BLOCKED"}


def store_readonly(root:Path,document:dict)->Path:
    if (document.get("schema")!=SCHEMA
        or document.get("production_p_matrix_authorized") is not False
        or document.get("telegram_signal_authorized") is not False
        or document.get("real_money")!="BLOCKED"):
        raise ValueError("UNSAFE_RESEARCH_EVIDENCE")
    at=datetime.fromisoformat(document["observed_at_utc"].replace("Z","+00:00"))
    day=at.astimezone(timezone(timedelta(hours=-5))).date().isoformat()
    name=("MATRIX_BETPLAY_RESEARCH_MARKET_"+
          at.strftime("%Y%m%dT%H%M%S%fZ")+"_"+document["quote_labels_sha256"][:12]+".json")
    path=root/"evidence"/"football_world_inventory"/day/name
    path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(document,ensure_ascii=False,sort_keys=True,indent=2).encode("utf-8")+b"\\n"
    if path.exists() and path.read_bytes()!=raw:
        raise ValueError("IMMUTABLE_BETPLAY_QUOTE_RECORD_CONFLICT")
    path.write_bytes(raw)
    return path


def visible_betplay_labels(page)->list[str]:
    """Collect only on-screen labelled market buttons; no account data."""
    return page.evaluate("""() => [...document.querySelectorAll('button[aria-label], [role="button"][aria-label]')]
       .filter(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
       .map(el => el.getAttribute('aria-label') || '')
       .filter(t => t.startsWith('Apuesta sobre ') && t.includes('Total de goles - Más de 2.5 en '))
       .slice(0,600)""")


def collect_page(page,source_url:str,root:Path,at:datetime)->dict:
    labels=visible_betplay_labels(page)
    doc=parse_labels(labels,source_url,at)
    dest=store_readonly(root,doc) if doc["quotes"] else None
    return {"status":"RESEARCH_QUOTES_VISIBLE_NOT_CANONICAL",
            "quote_count":doc["exact_visible_over25_quote_count"],
            "research_evidence_path":str(dest.relative_to(root)) if dest else None,
            "quoted_label_sha256":doc["quote_labels_sha256"],
            "telegram_signal_authorized":False}
