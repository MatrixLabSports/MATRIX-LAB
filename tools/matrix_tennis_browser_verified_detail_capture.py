"""User-authorized visible SofaScore Challenger match-page evidence.

Research only. Browser must be the existing user-authorized local CDP browser.
No provider backend APIs, stealth, score backfill, odds or betting.
Only authentic pre-kickoff details for exact two-source calendar name hints.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from tools.matrix_tennis_browser_challenger_pit_gate import AUTHORITIES, timestamp
from tools.matrix_tennis_exact_browser_crossmatch import fingerprint

ROOT = Path("evidence/tennis_calendar_reconciliation")
CAPTURE = Path("evidence/tennis_calendar_physical")
BOGOTA = ZoneInfo("America/Bogota")
# Visible country labels only: the original five-country subset caused false
# negatives when a participant's legitimate country was not in this list.
# This is not an identity crosswalk: the source must display the country text
# on that exact player profile link; missing or conflicting text fails closed.
COUNTRY_LABELS = {
    "Switzerland": ("Switzerland", "Suiza"),
    "Argentina": ("Argentina",),
    "Brazil": ("Brazil", "Brasil"),
    "Peru": ("Peru", "Perú"),
    "USA": ("USA", "United States", "Estados Unidos"),
    "France": ("France", "Francia"),
    "Italy": ("Italy", "Italia"),
    "Spain": ("Spain", "España"),
    "Germany": ("Germany", "Alemania"),
    "United Kingdom": ("United Kingdom", "Great Britain", "Reino Unido"),
    "Australia": ("Australia",),
    "Austria": ("Austria",),
    "Belgium": ("Belgium", "Bélgica"),
    "Canada": ("Canada", "Canadá"),
    "Chile": ("Chile",),
    "China": ("China",),
    "Colombia": ("Colombia",),
    "Croatia": ("Croatia", "Croacia"),
    "Czech Republic": ("Czech Republic", "Czechia", "Chequia"),
    "Denmark": ("Denmark", "Dinamarca"),
    "Ecuador": ("Ecuador",),
    "Finland": ("Finland", "Finlandia"),
    "Greece": ("Greece", "Grecia"),
    "Hungary": ("Hungary", "Hungría"),
    "India": ("India",),
    "Ireland": ("Ireland", "Irlanda"),
    "Israel": ("Israel",),
    "Japan": ("Japan", "Japón"),
    "Kazakhstan": ("Kazakhstan", "Kazajistán"),
    "Mexico": ("Mexico", "México"),
    "Netherlands": ("Netherlands", "Países Bajos"),
    "New Zealand": ("New Zealand", "Nueva Zelanda"),
    "Norway": ("Norway", "Noruega"),
    "Poland": ("Poland", "Polonia"),
    "Portugal": ("Portugal",),
    "Romania": ("Romania", "Rumanía"),
    "Serbia": ("Serbia",),
    "Slovakia": ("Slovakia", "Eslovaquia"),
    "Slovenia": ("Slovenia", "Eslovenia"),
    "South Africa": ("South Africa", "Sudáfrica"),
    "South Korea": ("South Korea", "Corea del Sur"),
    "Sweden": ("Sweden", "Suecia"),
    "Tunisia": ("Tunisia", "Túnez"),
    "Turkey": ("Turkey", "Türkiye", "Turquía"),
    "Ukraine": ("Ukraine", "Ucrania"),
    "Uruguay": ("Uruguay",),
    "Uzbekistan": ("Uzbekistan", "Uzbekistán"),
}
def visible_country_candidates(nodes: list[dict]) -> list[str]:
    # No global page text: a country must be attributable to this exact player.
    snippets = []
    for n in nodes:
        snippets.extend(str(n.get(key) or "") for key in ("name", "label"))
        snippets.extend(str(x) for x in (n.get("flag_alts") or []))
    result = []
    for canonical, aliases in COUNTRY_LABELS.items():
        if any(re.search(r"(?<![A-Za-zÀ-ÿ])" + re.escape(alias) +
                         r"(?![A-Za-zÀ-ÿ])", text, flags=re.IGNORECASE)
               for alias in aliases for text in snippets):
            result.append(canonical)
    return result

def source(root: Path, path: Path) -> tuple[dict, str]:
    p = root / path
    raw = p.read_bytes()
    if len(raw) > 8_000_000:
        raise ValueError("SOURCE_TOO_LARGE")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()

def eligible_priorities(root: Path, cross: dict) -> list[dict]:
    authority = {}
    for lane, path in AUTHORITIES.items():
        j, _ = source(root, Path(path))
        if (j.get("outcomes_used") is not False
            or j.get("post_cut_competitive_data_used") is not False
            or j.get("silent_imputation") is not False
            or j.get("real_money") != "BLOCKED"):
            raise ValueError("ORIGINAL_AUTHORITY_NOT_PIT_SAFE")
        authority[lane] = sorted(set(
            x["provider_display_name"]
            for x in j.get("records", [])
            if isinstance(x, dict) and x.get("provider_display_name")
        ))
    selected = []
    for x in cross.get("matches") or []:
        if not isinstance(x, dict):
            raise ValueError("INVALID_CROSSMATCH_ROW")
        tokens = Counter(x.get("source_name_token_key", "").split())
        matches = []
        for lane, names in authority.items():
            candidates = [(n, Counter(fingerprint(n))) for n in names]
            members = [(n, t) for n, t in candidates if t and t <= tokens]
            possible = [(a, b) for i, (a, ta) in enumerate(members)
                        for b, tb in members[i+1:] if ta+tb == tokens]
            if len(possible) == 1:
                matches.append({"surface_history_lane": lane,
                                "original_names": list(possible[0])})
        if matches:
            selected.append({**x, "original_history_pair_hints": matches})
    return sorted(selected, key=lambda r: (r["sofascore_id"], r["source_name_token_key"]))

def parse_visible(row: dict, ui: dict, day: str, observed_at: datetime) -> dict:
    sid = str(row["sofascore_id"])
    src = row["sofascore_url"]
    p = urlparse(src)
    if (p.scheme != "https" or p.hostname not in ("www.sofascore.com", "sofascore.com")
        or "/es/tennis/match/" not in p.path or p.fragment != "id:"+sid):
        raise ValueError("UNTRUSTED_SOURCE_MATCH_URL")
    if ui.get("page_url", "").split("#")[0] != src.split("#")[0]:
        raise ValueError("DETAIL_REDIRECT_WRONG_MATCH")
    links = ui.get("links")
    if not isinstance(links, list) or len(links) > 2500:
        raise ValueError("INVALID_VISIBLE_LINKS")
    players = {}
    for a in links:
        z = urlparse(str(a.get("url") or ""))
        if z.hostname not in ("www.sofascore.com", "sofascore.com"):
            continue
        m = re.fullmatch(r"/es/tennis/player/[^/]+/(\d+)", z.path)
        if m:
            players.setdefault(m.group(1), []).append(a)
    if len(players) != 2:
        raise ValueError("EXACT_TWO_VISIBLE_SOFA_PLAYER_PROFILES_REQUIRED")
    pairs = {tuple(sorted(h["original_names"])) for h in row.get("original_history_pair_hints", [])}
    if len(pairs) != 1:
        raise ValueError("ORIGINAL_PRE_CUT_PAIR_AMBIGUOUS")
    originals = next(iter(pairs))
    people = []
    for player_id, nodes in players.items():
        slug = urlparse(nodes[0]["url"]).path.split("/es/tennis/player/",1)[1].rsplit("/",1)[0]
        names = [n for n in originals if fingerprint(n) == fingerprint(slug)]
        if len(names) != 1:
            raise ValueError("PROFILE_SLUG_ORIGINAL_NAME_MISMATCH")
        name = names[0]
        if not any(n.get("name") or n.get("label") for n in nodes):
            raise ValueError("VISIBLE_PLAYER_PROFILE_LABEL_MISSING")
        country_candidates = visible_country_candidates(nodes)
        if len(country_candidates) != 1:
            raise ValueError("VISIBLE_PLAYER_COUNTRY_MISSING_OR_AMBIGUOUS")
        people.append({"name": name, "sofascore_player_id": player_id,
                       "profile_url": "https://www.sofascore.com/es/tennis/player/"
                           + urlparse(nodes[0]["url"]).path.split("/es/tennis/player/", 1)[1],
                       "country": country_candidates[0]})
    if tuple(sorted(fingerprint("-".join(p["name"] for p in people)))) != tuple(
            row["source_name_token_key"].split()):
        raise ValueError("EXACT_PLAYER_NAME_CROSSMATCH_DISAGREES")
    # Real SofaScore match pages may show "Orleans, France, Octavos de final"
    # rather than the legacy "Competición Tenis, Challenger 125, ...".
    # Challenger classification MUST come from the exact public tournament
    # URL, while the tournament and round must be present in the visible link.
    rounds = {"Primera ronda", "Segunda ronda", "Ronda de 32",
              "Octavos de final", "Cuartos de final",
              "Semifinal", "Semifinales", "Final"}
    # Multiple visible anchors can refer to the SAME event tournament:
    # e.g. "Orleans, France, Octavos de final" and
    # "Competición\\nTenis, Challenger 125, Orleans, France, Octavos de final".
    # Collapse only when exact trusted URL, tournament and round all agree.
    tournaments = {}
    for link in links:
        z = urlparse(str(link.get("url") or ""))
        if (z.scheme != "https" or z.hostname not in ("www.sofascore.com", "sofascore.com")
            or not z.path.startswith("/es/tennis/tournament/challenger/")):
            continue
        for field in ("label", "name"):
            candidate = re.sub(r"\s+", " ", str(link.get(field) or "")).strip()
            parts = [part.strip() for part in candidate.split(",")]
            if len(parts) >= 3 and parts[-1] in rounds and all(parts):
                prefix = (len(parts) >= 5 and parts[0] == "Competición Tenis"
                          and parts[1].startswith("Challenger"))
                tournament_name = ", ".join(parts[2:-1] if prefix else parts[:-1])
                if not tournament_name:
                    continue
                key = (link["url"], tournament_name.casefold(), parts[-1])
                previous = tournaments.get(key)
                # Prefer the shorter literal label as human-readable display;
                # both were on the same page, not synthesized by MATRIX.
                if previous is None or len(candidate) < len(previous[1]):
                    tournaments[key] = (link["url"], candidate, tournament_name, parts[-1])
    if len(tournaments) != 1:
        raise ValueError("EXACT_CHALLENGER_COMPETITION_LINK_REQUIRED")
    tournament_url, competition_label, tournament_name, tournament_round = next(iter(tournaments.values()))
    court_labels = [x for x in ("Dura indoor", "Tierra batida")
                    if x in (ui.get("visible_text") or "")]
    if len(court_labels) != 1:
        raise ValueError("EXACT_COURT_SURFACE_MISSING_OR_AMBIGUOUS")
    surface = {"Dura indoor": "Hard", "Tierra batida": "Clay"}[court_labels[0]]
    calendar = []
    for link in links:
        z = urlparse(str(link.get("url") or ""))
        if z.hostname != "calendar.google.com" or z.path != "/calendar/render":
            continue
        q = parse_qs(z.query)
        if q.get("action") != ["TEMPLATE"] or len(q.get("dates", [])) != 1:
            continue
        d = str(q["dates"][0])
        m = re.fullmatch(r"(\d{8}T\d{6}Z)/(\d{8}T\d{6}Z)", d)
        if not m:
            continue
        details = (q.get("details") or [""])[0]
        if details != src:
            continue
        calendar.append((m.group(1), " ".join(str(v or "") for v in (link.get("name"), link.get("label"))).strip()))
    calendar = list(dict.fromkeys(calendar))
    if len(calendar) != 1:
        raise ValueError("GOOGLE_CALENDAR_EXACT_EVENT_UTC_TOKEN_MISSING")
    utc_token, visible_label = calendar[0]
    kickoff = datetime.strptime(utc_token, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    local = kickoff.astimezone(BOGOTA)
    if local.date() != date.fromisoformat(day):
        raise ValueError("KICKOFF_OUTSIDE_BOGOTA_CALENDAR_DAY")
    expected_visible = f"{local.day}/{local.month}/{local.year} {local.hour}:{local.minute:02d}"
    if expected_visible not in visible_label:
        raise ValueError("UTC_TOKEN_DISAGREES_WITH_VISIBLE_LOCAL_CLOCK")
    if observed_at >= kickoff:
        raise ValueError("PROSPECTIVE_WINDOW_CLOSED")
    return {
        "sofascore_event_id": sid,
        "sofascore_url": src,
        "flashscore_url": row["flashscore_url"],
        "flashscore_mid": row["flashscore_mid"],
        "calendar_date_token": utc_token,
        "local_visible_date": f"{local.day}/{local.month}/{local.year}",
        "local_visible_time": f"{local.hour}:{local.minute:02d}",
        "kickoff_utc": kickoff.isoformat().replace("+00:00", "Z"),
        "competition_label": competition_label,
        "tournament_url": tournament_url,
        "tournament_name": tournament_name,
        "round": tournament_round,
        "challenger_category_evidenced_by_tournament_url": True,
        "court_label": court_labels[0],
        "surface": surface,
        "players": sorted(people, key=lambda x: x["name"]),
        "source_observation_utc": observed_at.isoformat(),
        "source_crossmatch_name_hint_only": True,
        "provider_player_id_equivalence_certified": False,
        "individual_start_and_surface_source_metadata_verified": True,
        "source_visible_match_fields": {
            "page_url": ui.get("page_url"),
            "profile_links": [{"url": a.get("url"), "name": a.get("name"),
                               "label": a.get("label"), "flag_alts": a.get("flag_alts")}
                              for a in links if "/es/tennis/player/" in str(a.get("url"))][:12],
            "tournament_link": tournament_url,
            "calendar_utc_start_token": utc_token,
            "calendar_local_visible_label": visible_label,
            "visible_court_label": court_labels[0],
        },
        "visible_page_evidence_sha256": hashlib.sha256(
            json.dumps(ui, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
    }

def public_visible_failure_clues(ui: dict | None) -> dict | None:
    """Small, source-bound evidence for failures; never infer missing fields.

    Only public visible SofaScore tennis player/tournament links are recorded.
    No page-wide body text, cookies, authorization headers or odds are saved.
    """
    if not isinstance(ui, dict):
        return None
    links = []
    for row in (ui.get("links") or [])[:2500]:
        if not isinstance(row, dict):
            continue
        uri = urlparse(str(row.get("url") or ""))
        if uri.scheme != "https" or uri.hostname not in ("sofascore.com", "www.sofascore.com"):
            continue
        if not (uri.path.startswith("/es/tennis/player/") or
                uri.path.startswith("/es/tennis/tournament/challenger/")):
            continue
        links.append({"url":uri.scheme+"://"+uri.netloc+uri.path,
                      "name":str(row.get("name") or "")[:150],
                      "label":str(row.get("label") or "")[:150],
                      "flag_alts":[str(x)[:90] for x in (row.get("flag_alts") or [])[:4]]})
        if len(links) >= 18:
            break
    # Expose only structured public calendar evidence; no redirect URLs,
    # no browser session data, no unbounded visible page text. Treat Google
    # Calendar's time as a candidate, NEVER as an admitted model kickoff.
    calendars = []
    for link in (ui.get("links") or [])[:2500]:
        if not isinstance(link, dict):
            continue
        uri = urlparse(str(link.get("url") or ""))
        if uri.hostname != "calendar.google.com" or uri.path != "/calendar/render":
            continue
        query = parse_qs(uri.query)
        details = (query.get("details") or [""])[0]
        dates = (query.get("dates") or [""])[0]
        calendars.append({
            "action_template":query.get("action")==["TEMPLATE"],
            "exact_utc_date_range_shape":bool(re.fullmatch(r"\\d{8}T\\d{6}Z/\\d{8}T\\d{6}Z",dates)),
            "utc_dates":dates[:33],
            "event_details_match_id":str(urlparse(details).fragment).startswith("id:"),
            "event_details_path":urlparse(details).path[:180],
            "label":str(link.get("name") or link.get("label") or "")[:140],
        })
        if len(calendars) >= 5:
            break
    visible_text = str(ui.get("visible_text") or "")
    # Bounded, source-visible court terms only. No names/score or general text.
    court_terms = []
    for term in ("Dura indoor", "Tierra batida", "Hard", "Clay", "pista dura",
                 "arcilla", "superficie", "court", "indoor", "outdoor"):
        if re.search(r"(?<![A-Za-z])"+re.escape(term)+r"(?![A-Za-z])",
                     visible_text, flags=re.IGNORECASE):
            court_terms.append(term)
    body = json.dumps(ui, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return {"visible_page_sha256":hashlib.sha256(body).hexdigest(),
            "visible_source_links":links,
            "public_calendar_link_count":len(calendars),
            "public_calendar_link_diagnostics":calendars,
            "visible_court_term_presence_only":court_terms,
            "not_individual_identity_certification":True}


def run(root: Path, day: str, endpoint: str, max_events: int = 6) -> dict:
    from playwright.sync_api import Error, sync_playwright
    date.fromisoformat(day)
    cross, cross_sha = source(root, ROOT/day/"MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json")
    if (cross.get("schema") != "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1"
        or cross.get("target_date_bogota") != day
        or cross.get("real_money") != "BLOCKED"
        or cross.get("source_event_equivalence_certified") is not False):
        raise ValueError("UNTRUSTED_TWO_SOURCE_MATCH_HINTS")
    candidates = eligible_priorities(root, cross)
    events, blocked = [], []
    with sync_playwright() as p:
        # The CDP browser is shared with the preceding calendar collector.
        # Bounded local reconnect handles contention; never changes provider
        # access rules, browser identity, or HTTP rate-limit outcomes.
        browser = None
        for attempt in range(3):
            try:
                browser = p.chromium.connect_over_cdp(endpoint, timeout=22000)
                break
            except Error:
                if attempt == 2:
                    raise
                __import__("time").sleep(2+attempt)
        if not browser.contexts:
            raise ValueError("AUTHORIZED_LOCAL_BROWSER_CONTEXT_MISSING")
        for row in candidates[:max_events]:
            page = browser.contexts[0].new_page()
            ui = None
            try:
                resp = page.goto(row["sofascore_url"], wait_until="domcontentloaded", timeout=18000)
                if resp and resp.status in (401, 403, 429):
                    blocked.append({"sofascore_id": row["sofascore_id"], "reason": "PROVIDER_REFUSED",
                                    "http_status": resp.status})
                    continue
                page.wait_for_timeout(1500)
                ui = page.evaluate("""() => ({
                    page_url: location.href,
                    visible_text: String(document.body?.innerText || '').slice(0,90000),
                    links: Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => a.getClientRects().length>0)
                        .filter(a => /\\/es\\/tennis\\/(player|tournament)|calendar\\.google\\.com/.test(a.href))
                        .slice(0,2500)
                        .map(a => ({url:a.href,
                            name:String(a.innerText||'').trim().slice(0,220),
                            label:String(a.getAttribute('aria-label')||'').trim().slice(0,220),
                            flag_alts:Array.from(a.querySelectorAll('img[alt]')).map(i=>String(i.alt||'')).slice(0,6)
                        }))
                })""")
                observed_at = datetime.now(timezone.utc)
                event = parse_visible(row, ui, day, observed_at)
                events.append(event)
            except (ValueError, Error, KeyError, TypeError, OSError) as exc:
                blocked.append({"sofascore_id": row["sofascore_id"],
                                "reason": str(exc) if isinstance(exc, ValueError)
                                          else type(exc).__name__,
                                "public_visible_failure_clues":public_visible_failure_clues(ui)})
            finally:
                page.close()
    report = {
        "schema": "MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1",
        "target_date_bogota": day,
        "capture_method": "AUTHORIZED_WINDOWS_CDP_SOFASCORE_VISIBLE_MATCH_PAGES",
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_order": ["SOFASCORE", "FLASHSCORE", "ORIGINAL_HISTORICAL_AUTHORITY"],
        "source_crossmatch_sha256": cross_sha,
        "data_origin": "SOFASCORE_VISIBLE_PAGE_ONLY",
        "calendar_backend_api_called": False,
        "original_authority_pair_candidates": len(candidates),
        "details_examined": min(max_events, len(candidates)),
        "individual_visible_metadata_verified_count": len(events),
        "blocked_reasons": blocked,
        "events": events,
        "model_parameters_modified": False,
        "new_model_observations_admitted": 0,
        "provider_identity_equivalence_certified": False,
        "original_model_feature_pit_equivalence_certified": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    target = root/CAPTURE/day/"sofascore_verified_match_details.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_file():
        old = json.loads(target.read_text(encoding="utf-8"))
        if (old.get("target_date_bogota") == day
            and len(old.get("events") or []) > len(events)):
            report["status"] = "REJECTED_REGRESSED_DETAILS_PRESERVED"
            return report
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)+"\n",
                      encoding="utf-8")
    report["status"] = ("VERIFIED_VISIBLE_CHALLENGER_METADATA_RESEARCH_ONLY" if events
                        else "NO_AUTHENTIC_VISIBLE_CHALLENGER_DETAILS_VERIFIED")
    return report

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--root", type=Path, default=Path.cwd())
    p.add_argument("--cdp", default="http://127.0.0.1:9222")
    p.add_argument("--max-events", type=int, default=6)
    args = p.parse_args()
    if not 1 <= args.max_events <= 12:
        raise SystemExit("DETAIL_CAPTURE_BOUNDED_1_TO_12")
    report = run(args.root, args.date, args.cdp, args.max_events)
    print(json.dumps({k: v for k, v in report.items()
        if k in ("status", "details_examined", "individual_visible_metadata_verified_count",
                 "original_authority_pair_candidates", "blocked_reasons", "real_money")},
        ensure_ascii=False, sort_keys=True))
    if not report["individual_visible_metadata_verified_count"]:
        raise SystemExit("NO_AUTHENTIC_CHALLENGER_DETAILS_FAIL_CLOSED")

if __name__ == "__main__":
    main()
