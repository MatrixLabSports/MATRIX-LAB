from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

HARD = {"hard", "i.hard", "indoor hard", "indoor_hard"}
CLAY = {"clay", "red clay", "green clay"}
LIVE_TOKENS = {"live", "in progress", "in_progress", "playing", "set1", "set2", "set3", "set4", "set5"}
CANCEL_TOKENS = {"cancel", "cancelled", "canceled", "retired", "walkover", "walk over", "withdrawn"}

def _fold(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = re.sub(r"[^a-z0-9/ -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _tokens(value: Any) -> set[str]:
    return {x for x in re.split(r"[\s/.]+", _fold(value)) if len(x) >= 2 and not x.isdigit()}

def _parse_aware(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)

def _browser_rows(reconciliation: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    def add(label: str, raw: str) -> None:
        key = _fold(raw)
        if not key or key in seen:
            return
        seen.add(key)
        rows.append({"browser_status": label, "raw": raw, "key": key})
    for row in reconciliation.get("confirmed_both") or []:
        if isinstance(row, Mapping):
            add("CONFIRMED_BOTH", str(row.get("flashscore") or row.get("sofascore") or ""))
    for row in reconciliation.get("sofascore_only") or []:
        if isinstance(row, Mapping):
            add("SOFASCORE_ONLY", str(row.get("sofascore") or ""))
    for row in reconciliation.get("flashscore_only") or []:
        if isinstance(row, Mapping):
            add("FLASHSCORE_ONLY", str(row.get("flashscore") or ""))
    for row in reconciliation.get("ambiguous") or []:
        if isinstance(row, Mapping):
            add("AMBIGUOUS", str(row.get("flashscore") or row.get("sofascore") or ""))
    return rows

def _browser_match(event: Mapping[str, Any], rows: list[dict[str, Any]]) -> tuple[str, str | None, int | None]:
    p1 = str((event.get("player1") or {}).get("name") or "")
    p2 = str((event.get("player2") or {}).get("name") or "")
    t1, t2 = _tokens(p1), _tokens(p2)
    if not t1 or not t2:
        return "NONE", None, None
    candidates: list[tuple[float, int]] = []
    for idx, row in enumerate(rows):
        body = _tokens(row["raw"])
        h1 = len(t1 & body) / len(t1)
        h2 = len(t2 & body) / len(t2)
        if h1 >= 0.5 and h2 >= 0.5:
            candidates.append(((h1 + h2) / 2.0, idx))
    candidates.sort(reverse=True)
    if not candidates:
        return "NONE", None, None
    score, idx = candidates[0]
    if len(candidates) > 1 and candidates[1][0] >= score - 0.05:
        return "AMBIGUOUS", rows[idx]["raw"], idx
    return rows[idx]["browser_status"], rows[idx]["raw"], idx

def _cancelled(provider_status: Any, browser_raw: Any) -> bool:
    token = _fold(provider_status) + " " + _fold(browser_raw)
    return any(x in token for x in CANCEL_TOKENS) or "cancelado" in token

def _live(provider_status: Any) -> bool:
    token = _fold(provider_status)
    return any(x in token for x in LIVE_TOKENS)

def _surface_class(value: Any) -> str:
    token = _fold(value)
    if token in HARD or "hard" in token:
        return "HARD"
    if token in CLAY or "clay" in token:
        return "CLAY"
    return "OTHER"

def _identity_fixed(event: Mapping[str, Any]) -> bool:
    p1 = event.get("player1") if isinstance(event.get("player1"), Mapping) else {}
    p2 = event.get("player2") if isinstance(event.get("player2"), Mapping) else {}
    return bool(str(p1.get("id") or "").strip() and str(p2.get("id") or "").strip()
                and str(p1.get("name") or "").strip() and str(p2.get("name") or "").strip())

def _classify(event: Mapping[str, Any], browser_status: str, browser_raw: str | None, as_of: datetime) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if _cancelled(event.get("provider_status"), browser_raw):
        return "CANCELLED", ["EVENT_CANCELLED_OR_NONSTANDARD_TERMINAL"]
    if not _identity_fixed(event):
        return "IDENTITY_NOT_FIXED", ["PROVIDER_PLAYER_IDENTITY_INCOMPLETE"]
    start = _parse_aware(event.get("event_start_utc"))
    local = _parse_aware(event.get("event_start_bogota"))
    if start is None or local is None:
        return "START_NOT_CERTIFIED", ["TIMEZONE_AWARE_START_NOT_PROVEN"]
    if _live(event.get("provider_status")) or start <= as_of:
        return "LIVE_ONLY", ["POST_START_PROSPECTIVE_FREEZE_FORBIDDEN"]
    fmt = str(event.get("event_format") or "").upper()
    surface = _surface_class(event.get("surface"))
    if fmt != "SINGLES":
        blockers.append("EVENT_FORMAT_NOT_SINGLES")
    if surface == "OTHER":
        blockers.append("SURFACE_OUTSIDE_HARD_CLAY")
    if blockers:
        return "OUT_OF_DOMAIN", blockers
    if surface == "HARD":
        return "ELIGIBLE_HARD", []
    if surface == "CLAY":
        return "ELIGIBLE_CLAY", []
    return "OUT_OF_DOMAIN", ["UNREACHABLE_SURFACE_CLASS"]

def build_canonical_inventory(
    reconciliation: Mapping[str, Any],
    rapid_inventory: Mapping[str, Any],
    *,
    as_of_utc: str,
) -> dict[str, Any]:
    if reconciliation.get("target_date_bogota") != rapid_inventory.get("target_date_bogota"):
        raise ValueError("TARGET_DATE_MISMATCH")
    as_of = _parse_aware(as_of_utc)
    if as_of is None:
        raise ValueError("AS_OF_UTC_MUST_BE_TIMEZONE_AWARE")
    browser_rows = _browser_rows(reconciliation)
    used_browser: set[int] = set()
    rows: list[dict[str, Any]] = []
    for event in rapid_inventory.get("events") or []:
        if not isinstance(event, Mapping):
            continue
        bstatus, braw, bidx = _browser_match(event, browser_rows)
        if bidx is not None:
            used_browser.add(bidx)
        classification, blockers = _classify(event, bstatus, braw, as_of)
        model = event.get("model_derivation") if isinstance(event.get("model_derivation"), Mapping) else {}
        browser_seen = bstatus in {"CONFIRMED_BOTH", "SOFASCORE_ONLY", "FLASHSCORE_ONLY"}
        cor_candidate = (
            classification == "ELIGIBLE_HARD"
            and bool(model.get("domain_candidate"))
            and browser_seen
        )
        row = dict(event)
        row.update({
            "canonical_status": classification,
            "canonical_blockers": blockers,
            "browser_match_status": bstatus,
            "browser_match_raw": braw,
            "browser_first_seen": browser_seen,
            "cor0203_preregister_candidate": cor_candidate,
            "automatic_model_feed": False,
            "p_matrix_generated": False,
        })
        rows.append(row)

    for idx, brow in enumerate(browser_rows):
        if idx in used_browser:
            continue
        cancelled = "cancelado" in _fold(brow["raw"])
        rows.append({
            "source_provider": "browser_only",
            "source_event_id": None,
            "browser_match_status": brow["browser_status"],
            "browser_match_raw": brow["raw"],
            "browser_first_seen": True,
            "canonical_status": "CANCELLED" if cancelled else "START_NOT_CERTIFIED",
            "canonical_blockers": (
                ["EVENT_CANCELLED_OR_NONSTANDARD_TERMINAL"]
                if cancelled else
                ["API_START_SURFACE_IDENTITY_NOT_YET_RECONCILED"]
            ),
            "cor0203_preregister_candidate": False,
            "automatic_model_feed": False,
            "p_matrix_generated": False,
        })

    counts = Counter(str(row.get("canonical_status")) for row in rows)
    cor_candidates = [
        row.get("source_event_id")
        for row in rows if row.get("cor0203_preregister_candidate")
    ]
    return {
        "schema": "MATRIX_TENNIS_27OCT_CANONICAL_INVENTORY_V1",
        "generated_at_utc": as_of.isoformat(),
        "target_date_bogota": reconciliation.get("target_date_bogota"),
        "status": "PASS_CANONICAL_INVENTORY_FAIL_CLOSED",
        "source_order": ["SOFASCORE", "FLASHSCORE", "RAPIDAPI_TENNIS", "OFFICIAL_SOURCES_IF_NEEDED"],
        "browser_observed_unique": len(browser_rows),
        "rapidapi_provider_inventory_count": int(rapid_inventory.get("world_calendar_inventory_count") or 0),
        "canonical_row_count": len(rows),
        "classification_counts": dict(sorted(counts.items())),
        "cor0203_preregister_candidate_count": len(cor_candidates),
        "cor0203_preregister_source_event_ids": cor_candidates,
        "rows": rows,
        "governance": {
            "world_complete_certified": False,
            "browser_first_required_for_cor0203_preregister": True,
            "provider_inventory_complete": bool(rapid_inventory.get("provider_inventory_complete")),
            "missing_not_zero": True,
            "no_silent_imputation": True,
            "post_start_backfill_forbidden": True,
            "settlement_final_only": True,
            "odds_generate_p_matrix": False,
            "metrics_opened": False,
            "automatic_model_feed": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--reconciliation", required=True)
    p.add_argument("--rapidapi-inventory", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--as-of-utc")
    args = p.parse_args()
    recon = json.loads(Path(args.reconciliation).read_text(encoding="utf-8"))
    rapid = json.loads(Path(args.rapidapi_inventory).read_text(encoding="utf-8"))
    as_of = args.as_of_utc or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    result = build_canonical_inventory(recon, rapid, as_of_utc=as_of)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "target_date_bogota": result["target_date_bogota"],
        "browser_observed_unique": result["browser_observed_unique"],
        "rapidapi_provider_inventory_count": result["rapidapi_provider_inventory_count"],
        "canonical_row_count": result["canonical_row_count"],
        "classification_counts": result["classification_counts"],
        "cor0203_preregister_candidate_count": result["cor0203_preregister_candidate_count"],
        "real_money": "BLOCKED",
    }, sort_keys=True))

if __name__ == "__main__":
    main()
