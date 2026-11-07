"""Fail-closed browser-first source-link reconciliation for the 2026-11-03 football calendar.

Source links are observations, NOT canonical fixtures, predictions, verified odds
or proof of event date/time. The Flashscore calendar date selector is page-level
context only; the individual Flashscore event dates are not certified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATE = "2026-11-03"
DATE_TEXT = "3/11/26"
SOURCES = ["SOFASCORE", "FLASHSCORE", "APIS"]
SOFA_SCHEMA = "MATRIX_20261103_OPERA_SOFASCORE_LINK_CAPTURE_V1"
FLASH_SCHEMA = "MATRIX_20261103_OPERA_FLASHSCORE_LINK_CAPTURE_V1"
FLASH_DATE_LABEL = "martes, 3 de noviembre de 2026"
SOFA_URL = re.compile(r"^https://www\.sofascore\.com/es/football/match/([^/?#]+)/[^/?#]+#id:(\d+)$")
FLASH_URL = re.compile(r"^https://www\.flashscore\.co/partido/futbol/([^/?#]+)/([^/?#]+)/?(?:\?[^#]*)?$")
DATE_LABEL = re.compile(r"^3/11/26(?:\s|$)")
CLOCK_LABEL = re.compile(r"^3/11/26\s+(\d{1,2}):(\d\d)(?:\s|$)")
TEAM_CODE = re.compile(r"-[A-Za-z0-9]{8}$")


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def guarded(source: dict, expected_schema: str, expected_source: str) -> None:
    require(isinstance(source, dict), "SOURCE_OBJECT_INVALID")
    require(source.get("schema") == expected_schema, "SOURCE_SCHEMA_INVALID")
    require(source.get("source") == expected_source, "SOURCE_IDENTITY_INVALID")
    require(source.get("target_date_bogota") == DATE, "TARGET_DATE_INVALID")
    require(source.get("source_order") == SOURCES, "SOURCE_ORDER_INVALID")
    g = source.get("governance")
    require(isinstance(g, dict), "MISSING_GOVERNANCE")
    require(g.get("real_money") == "BLOCKED", "REAL_MONEY_NOT_BLOCKED")
    for name in ("full_world_schedule_certified", "unique_fixtures_cross_source_certified",
                 "clock_utc_certified", "calibrated_probability_authorized",
                 "market_quotes_certified", "telegram_signal_authorized",
                 "model_calibration_changed", "automatic_wagering"):
        require(g.get(name) is False, "GOVERNANCE_GATE_UNSAFE_" + name)


def source_sofascore(data: dict) -> tuple[list[dict], dict]:
    guarded(data, SOFA_SCHEMA, "SOFASCORE")
    require(data.get("source_page_url") == "https://www.sofascore.com/es/football/2026-11-03",
            "SOFASCORE_DATE_PAGE_INVALID")
    items = data.get("observations")
    require(isinstance(items, list), "SOFA_OBSERVATIONS_NOT_LIST")
    require(data.get("distinct_observed_match_urls") == len(items), "SOFA_COUNT_MISMATCH")
    urls, event_ids = set(), set()
    dated, timed, date_only, undated = [], [], [], []
    out = []
    for item in items:
        require(isinstance(item, dict), "SOFA_LINK_INVALID")
        name, url = item.get("display_name"), item.get("source_url")
        require(isinstance(name, str) and isinstance(url, str), "SOFA_LINK_TEXT_INVALID")
        match = SOFA_URL.fullmatch(url)
        require(match is not None, "SOFA_URL_INVALID")
        slug, eid = match.groups()
        require(item.get("source_event_id") == eid, "SOFA_EVENT_ID_NOT_GROUNDED")
        require(url not in urls and eid not in event_ids, "SOFA_DUPLICATE_LINK_OR_EVENT")
        urls.add(url)
        event_ids.add(eid)
        has_date = DATE_LABEL.match(name) is not None
        has_time = CLOCK_LABEL.match(name) if has_date else None
        require(item.get("explicit_target_date_label") is has_date, "SOFA_DATE_FLAG_WRONG")
        require(item.get("visible_kickoff_clock") is (has_time is not None),
                "SOFA_KICKOFF_FLAG_WRONG")
        if has_date:
            dated.append(eid)
            if has_time:
                hour, minute = map(int, has_time.groups())
                require(hour <= 23 and minute <= 59, "INVALID_VISIBLE_TIME")
                timed.append(eid)
            else:
                date_only.append(eid)
        else:
            undated.append(eid)
        out.append({"id": eid, "slug": slug, "name": name, "url": url,
                    "date": has_date, "clock": has_time is not None})
    require(data.get("unique_sofascore_event_ids") == len(event_ids), "SOFA_ID_COUNT_MISMATCH")
    for key, actual in (
        ("explicit_target_date_labels", len(dated)),
        ("explicit_date_with_visible_clock", len(timed)),
        ("explicit_date_without_visible_clock", len(date_only)),
        ("without_explicit_target_date", len(undated)),
    ):
        require(data.get(key) == actual, "SOFA_COUNT_WRONG_" + key)
    return out, {"observed_urls": len(urls), "unique_event_ids": len(event_ids),
                 "explicit_date": len(dated), "date_with_visible_clock": len(timed),
                 "date_without_visible_clock": len(date_only),
                 "no_explicit_date": len(undated),
                 "date_without_visible_clock_event_ids": date_only,
                 "no_explicit_date_event_ids": undated}


def source_flashscore(data: dict) -> list[dict]:
    guarded(data, FLASH_SCHEMA, "FLASHSCORE")
    require(data.get("date_selector_accessibility_label") == FLASH_DATE_LABEL,
            "FLASH_CALENDAR_DATE_CONTEXT_INVALID")
    require(data.get("individual_fixture_date_certified") is False,
            "FLASH_INDIVIDUAL_DATE_OVERCLAIM")
    require(data.get("source_page_url") == "https://www.flashscore.co/",
            "FLASH_PAGE_INVALID")
    items = data.get("observations")
    require(isinstance(items, list), "FLASH_OBSERVATIONS_NOT_LIST")
    require(data.get("distinct_observed_match_urls") == len(items), "FLASH_COUNT_MISMATCH")
    urls, out = set(), []
    for item in items:
        require(isinstance(item, dict), "FLASH_LINK_INVALID")
        name, url = item.get("display_name"), item.get("source_url")
        require(isinstance(name, str) and isinstance(url, str), "FLASH_LINK_TEXT_INVALID")
        match = FLASH_URL.fullmatch(url)
        require(match is not None, "FLASH_URL_INVALID")
        require(url not in urls, "FLASH_URL_DUPLICATE")
        urls.add(url)
        teams = [TEAM_CODE.sub("", x) for x in match.groups()]
        out.append({"name": name, "url": url, "teams": teams})
    return out


def anchored_span(whole: str, piece: str) -> tuple[int, int] | None:
    if len(piece) < 4:
        return None
    start = 0
    while True:
        pos = whole.find(piece, start)
        if pos < 0:
            return None
        end = pos + len(piece)
        if (pos == 0 or whole[pos - 1] == "-") and (
            end == len(whole) or whole[end] == "-"
        ):
            return pos, end
        start = pos + 1


def reconcile(sofa: dict, flash: dict) -> dict:
    sofa_items, stats = source_sofascore(sofa)
    flash_items = source_flashscore(flash)
    pairs = []
    for f in flash_items:
        a, b = f["teams"]
        if len(a) < 4 or len(b) < 4 or a == b:
            continue
        for s in sofa_items:
            if not (s["date"] and s["clock"]):
                continue
            p, q = anchored_span(s["slug"], a), anchored_span(s["slug"], b)
            if p is not None and q is not None and (p[1] <= q[0] or q[1] <= p[0]):
                pairs.append({
                    "sofascore_event_id": s["id"],
                    "sofascore_name": s["name"],
                    "sofascore_url": s["url"],
                    "flashscore_name": f["name"],
                    "flashscore_url": f["url"],
                    "link_identity_basis":
                        "BOTH_FLASH_TEAM_SLUGS_ANCHORED_NONOVERLAPPING_IN_SOFA_MATCH_SLUG",
                    "fixture_certified": False,
                    "individual_flashscore_event_date_certified": False,
                    "utc_kickoff_certified": False,
                })
    sofa_edges, flash_edges = {}, {}
    for p in pairs:
        s, f = p["sofascore_url"], p["flashscore_url"]
        sofa_edges[s] = sofa_edges.get(s, 0) + 1
        flash_edges[f] = flash_edges.get(f, 0) + 1
    singles, ambiguous = [], []
    for p in pairs:
        (singles if sofa_edges[p["sofascore_url"]] == 1
         and flash_edges[p["flashscore_url"]] == 1 else ambiguous).append(p)
    singles.sort(key=lambda x: (x["sofascore_event_id"], x["flashscore_url"]))
    ambiguous.sort(key=lambda x: (x["sofascore_event_id"], x["flashscore_url"]))
    return {
        "schema": "MATRIX_20261103_OPERA_FOOTBALL_LINK_RECONCILIATION_V1",
        "target_date_bogota": DATE,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "LINK_IDENTITY_CANDIDATES_ONLY_NOT_CERTIFIED_FIXTURES",
        "source_order": SOURCES,
        "sofascore_counts": stats,
        "flashscore_visible_links": len(flash_items),
        "flashscore_page_date_selector": FLASH_DATE_LABEL,
        "candidate_pair_count_before_one_to_one_filter": len(pairs),
        "one_to_one_link_identity_candidate_count": len(singles),
        "ambiguous_link_pair_count": len(ambiguous),
        "one_to_one_link_identity_candidates": singles,
        "ambiguous_link_pairs": ambiguous,
        "independent_api_fixture_identity_verified": False,
        "all_candidate_pairs_are_not_certified_fixtures": True,
        "flashscore_individual_event_date_certified": False,
        "sofascore_visible_clock_is_not_utc_certification": True,
        "exact_odds_verified": False,
        "model_probability_authorized": False,
        "telegram_signals_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "calibration_parameters_modified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sofascore", required=True, type=Path)
    parser.add_argument("--flashscore", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    s_bytes, f_bytes = args.sofascore.read_bytes(), args.flashscore.read_bytes()
    result = reconcile(json.loads(s_bytes), json.loads(f_bytes))
    result["source_sha256"] = {
        "sofascore": hashlib.sha256(s_bytes).hexdigest(),
        "flashscore": hashlib.sha256(f_bytes).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False,
                                    sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "sofascore_links": result["sofascore_counts"]["observed_urls"],
        "flashscore_links": result["flashscore_visible_links"],
        "link_identity_candidates": result["one_to_one_link_identity_candidate_count"],
        "ambiguous_pairs": result["ambiguous_link_pair_count"],
        "telegram_signals_authorized": result["telegram_signals_authorized"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
