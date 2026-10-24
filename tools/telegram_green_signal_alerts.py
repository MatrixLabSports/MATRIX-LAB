# MATRIX_STAKE_GUARDRAIL_PHYSICAL_RECHECK 2026-10-17T20:53Z
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from difflib import SequenceMatcher
import unicodedata
from zoneinfo import ZoneInfo

import requests

from app.research.football.correlated_exposure import (
    CorrelationLimits,
    ExposureRecord,
    assess_correlated_exposure,
)
from app.research.football.correlated_risk_calibration import (
    calibrate_correlated_risk_from_ledger,
    calibration_evidence,
)
from app.research.football.sharp_consensus import assess_sharp_consensus
from app.market.colombia_bookmakers import EXECUTION_BOOKMAKERS

from app.research.football.correlated_exposure import (
    assess_paper_correlated_exposure,
    calibrate_paper_correlated_exposure,
)

BOGOTA = ZoneInfo("America/Bogota")
FOOTBALL_ROOT = Path("evidence/api_football/daily_prematch_reports")
TENNIS_ROOT = Path("evidence/tennis_signals")
LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
SENT_RECOVERY_OVERRIDES = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SENT_RECOVERY_OVERRIDES.json")
CORRELATED_RISK_EVIDENCE = Path("evidence/notifications/telegram/MATRIX_CORRELATED_RISK_CALIBRATION_LAST.json")
BLOCKER_AUDIT_EVIDENCE = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_LAST.json")
EV_MARGINAL_LAB_EVIDENCE = Path("evidence/notifications/telegram/MATRIX_EV_MARGINAL_SHADOW_LAB_LAST.json")
PHYSICAL_BOOK_QUOTE_ROOT = Path("evidence/football_world_inventory")
PHYSICAL_BOOK_QUOTE_MAX_AGE_MINUTES = 30

GREEN_STATUSES = {
    "SEÑAL_VERDE_SIMULADA_Y_APUESTA_USUARIO_EJECUTADA",
    "BET_SHADOW_PHYSICAL",
    "SEÑAL_VERDE_SIMULADA",
}
FINAL_STATUSES = {"FT", "AET", "PEN"}
VOID_STATUSES = {"PST", "CANC", "ABD"}
POLICY_BOOKS = {
    **EXECUTION_BOOKMAKERS,
    "mryoker": ("mryoker", "mr yoker", "mr. yoker"),
    "rushbet": ("rushbet", "rush bet"),
    "sportium": ("sportiumco", "sportium"),
    "stake": ("stake", "stakeco", "stake colombia"),
    "wplay": ("wplay", "w play"),
    "yajuego": ("yajuego", "ya juego"),
}
SHARP_REFERENCE_BOOKS = {"pinnacle", "circa", "betfair"}
MARKET_CONTEXT_BOOKS = {"fanduel"}
REFERENCE_BOOKS = SHARP_REFERENCE_BOOKS | MARKET_CONTEXT_BOOKS
MARKET_KEY = "Goles totales Más/Menos"
SELECTION_KEY = "Más de 2.5"

PAPER_BANKROLL_INITIAL_COP = 5_000_000.0
PAPER_UNIT_FRACTION = 0.005
PAPER_UNIT_COP = PAPER_BANKROLL_INITIAL_COP * PAPER_UNIT_FRACTION
PAPER_MAX_OPEN_EXPOSURE_FRACTION = 0.40
PAPER_DAILY_BASE_EXPOSURE_FRACTION = 0.30
PAPER_DAILY_MAX_EXPOSURE_FRACTION = 0.40
PAPER_HIGH_CONF_MIN_STAKE3 = 5
PAPER_HIGH_CONF_MIN_TIER23_SHARE = 0.40
PAPER_STAKE_LEVELS = {1: 1.0, 2: 2.0, 3: 3.0}
# Temporary risk override after physical ledger audit on 17-OCT-2026:
# variable 2u/3u sizing amplified losses while the high-P/high-EV tail
# remains insufficiently calibrated. Preserve model/signal gates, but cap
# paper exposure at 1u until the risk override is explicitly retired.
PAPER_STAKE_MAX_LEVEL = 1
PAPER_STAKE_RISK_OVERRIDE = "TEMPORARY_FLAT_1U_CAP_17OCT2026"
# MATRIX_STAKE_GUARDRAIL_PHYSICAL_PROOF_TRIGGER 17OCT2026
# MATRIX_STAKE_GUARDRAIL_VERIFICATION_TRIGGER 17OCT2026_1553_BOG
GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES = 120
PAPER_MAX_SIGNALS_PER_LEAGUE_DAY = 3
ODDS_API_NET_BASE = "https://api.odds-api.net/v1"
ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS = 7200
SIGNAL_QUALITY_MIN_P_MATRIX = 0.60
SIGNAL_QUALITY_MIN_REVALIDATED_EV = 0.05
SIGNAL_QUALITY_POLICY = "API_COST_RECOVERY_PRECISION_V1"
EV_MARGINAL_LAB_MIN_EV_EXCLUSIVE = 0.0
EV_MARGINAL_LAB_MAX_EV_EXCLUSIVE = 0.05
EV_MARGINAL_LAB_TARGET_OBSERVATIONS = 300


def is_ev_marginal_lab_candidate(p_matrix: float, decimal_odds: float, ev: float) -> bool:
    return (
        float(p_matrix) >= SIGNAL_QUALITY_MIN_P_MATRIX
        and float(decimal_odds) > 1.50
        and EV_MARGINAL_LAB_MIN_EV_EXCLUSIVE < float(ev) < EV_MARGINAL_LAB_MAX_EV_EXCLUSIVE
    )


def ev_marginal_band(ev: float) -> str:
    value = float(ev)
    if not EV_MARGINAL_LAB_MIN_EV_EXCLUSIVE < value < EV_MARGINAL_LAB_MAX_EV_EXCLUSIVE:
        raise ValueError("EV_OUTSIDE_MARGINAL_LAB")
    return "EV_0_2PCT" if value < 0.02 else "EV_2_5PCT"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def persist_ledger_checkpoint(ledger: dict[str, Any]) -> None:
    """Atomically persist confirmed Telegram delivery state before later work.

    This closes the local durability gap where Telegram accepted a message but
    a later exception prevented the end-of-run ledger write.
    """
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(LEDGER.suffix + ".tmp")
    tmp.write_text(
        json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, LEDGER)


def over25_signal_governance_authorized() -> tuple[bool, dict[str, Any]]:
    path = Path("evidence/api_football/governance/over_2_5_p_matrix_promotion.json")
    promotion = load_json(path, {})
    checks = {
        "market": promotion.get("market") == "OVER_2_5",
        "promotion_status": promotion.get("promotion_status") == "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY",
        "engine_executable": promotion.get("engine_executable_for_p_matrix") is True,
        "scope_signal_only": promotion.get("promotion_scope") == "MARKET_SCOPED_SIGNAL_GENERATION_NOT_REAL_MONEY",
        "real_money_blocked": (promotion.get("protections") or {}).get("real_money") == "BLOCKED",
        "automatic_wagering_false": (promotion.get("protections") or {}).get("automatic_wagering") is False,
    }
    return all(checks.values()), {
        "promotion_artifact": str(path),
        "promotion_status": promotion.get("promotion_status"),
        "checks": checks,
        "real_money": "BLOCKED",
    }


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None or dt.utcoffset() is None:
        return None
    return dt.astimezone(timezone.utc)


def fmt_bogota(value: Any) -> str:
    dt = parse_dt(value)
    if dt is None:
        return "Sin hora"
    return dt.astimezone(BOGOTA).strftime("%d/%m/%Y %I:%M %p")


def signal_key(fixture_id: Any, market: str = MARKET_KEY, selection: str = SELECTION_KEY) -> str:
    raw = f"{fixture_id}|{market}|{selection}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def bookmaker_key(name: Any) -> str | None:
    n = norm(name)
    for key, tokens in POLICY_BOOKS.items():
        if any(norm(t) in n for t in tokens):
            return key
    return None


def odd(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if x > 1.0 else None


def send_telegram(session: requests.Session, token: str, chat_id: str, text: str) -> int:
    response = session.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat_id, "text": text},
        timeout=(10, 90),
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if response.status_code >= 300 or payload.get("ok") is not True:
        raise RuntimeError(f"TELEGRAM_SEND_FAILED:{response.status_code}:{payload}")
    result = payload.get("result") or {}
    return int(result["message_id"])


def execution_from_row(row: dict[str, Any]) -> dict[str, Any] | None:
    obj = row.get("betplay_physical_execution") or row.get("user_real_money_execution")
    return dict(obj) if isinstance(obj, dict) else None


def browser_candidate(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    status = str(row.get("final_shadow_status") or "")
    eligible_green = status in GREEN_STATUSES
    try:
        p = float(row.get("p_matrix_over_2_5"))
    except Exception:
        return None
    execution = execution_from_row(row)
    house = (
        row.get("best_physically_verified_house")
        or (execution or {}).get("bookmaker")
        or row.get("house")
        or (row.get("api_feed_quote") or {}).get("bookmaker_name")
        or "Casa físicamente verificada"
    )
    dec = odd(
        row.get("best_physically_verified_decimal_odds")
        or row.get("physical_decimal_odds")
        or (execution or {}).get("decimal_odds")
        or (row.get("api_feed_quote") or {}).get("decimal_odds")
    )
    if dec is None:
        return None
    ev = row.get("best_physically_verified_ev")
    if ev is None:
        ev = row.get("ev")
    try:
        ev = float(ev)
    except Exception:
        ev = p * dec - 1.0
    return {
        "sport": "football",
        "fixture_id": str(row.get("fixture_id") or ""),
        "match": row.get("match"),
        "league_id": str(row.get("league_id") or row.get("league") or ""),
        "market": "Más de 2.5 goles",
        "market_key": MARKET_KEY,
        "selection_key": SELECTION_KEY,
        "p_matrix": p,
        "house": str(house),
        "odds": dec,
        "ev": ev,
        "kickoff": row.get("kickoff_bogota") or row.get("kickoff_utc"),
        "source": str(path),
        "source_priority": 30,
        "physical_quote_verified": True,
        "eligible_green": eligible_green,
        "source_status": status,
        "execution": execution,
    }


def quote_freeze_candidate(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    if str(row.get("decision") or "") != "BET_SHADOW":
        return None
    offer = row.get("best_policy_offer")
    if not isinstance(offer, dict):
        return None
    try:
        p = float(row.get("p_matrix") if row.get("p_matrix") is not None else row.get("p_over_2_5"))
    except Exception:
        return None
    dec = odd(offer.get("decimal_odds"))
    if dec is None:
        return None
    ev = float(offer.get("ev") if offer.get("ev") is not None else p * dec - 1.0)
    return {
        "sport": "football",
        "fixture_id": str(row.get("fixture_id") or ""),
        "match": row.get("match"),
        "league_id": str(row.get("league_id") or row.get("league") or ""),
        "market": "Más de 2.5 goles",
        "market_key": MARKET_KEY,
        "selection_key": SELECTION_KEY,
        "p_matrix": p,
        "house": str(offer.get("bookmaker_name") or "Casa de política"),
        "odds": dec,
        "ev": ev,
        "kickoff": row.get("kickoff_utc"),
        "source": str(path),
        "source_priority": 20,
        "physical_quote_verified": True,
        "eligible_green": True,
        "execution": None,
    }


def shadow_watch_candidate(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    """Promote any scored P_MATRIX row that can still pass the immutable quality gate.

    Price is intentionally optional here. Exact executable odds are acquired only
    in the final prematch revalidation window from an authorized policy house.
    """
    try:
        p = float(row.get("p_over_2_5"))
    except Exception:
        return None
    if p < SIGNAL_QUALITY_MIN_P_MATRIX:
        return None
    fixture_id = str(row.get("fixture_id") or "").strip()
    kickoff = row.get("kickoff_utc")
    if not fixture_id or parse_dt(kickoff) is None:
        return None
    offer = row.get("best_policy_offer")
    initial_odds = None
    initial_ev = None
    initial_house = "MULTIBOOK_REVALIDATION"
    physical = False
    if isinstance(offer, dict):
        initial_odds = odd(offer.get("decimal_odds"))
        if initial_odds is not None:
            initial_ev = float(offer.get("ev") if offer.get("ev") is not None else p * initial_odds - 1.0)
            initial_house = str(offer.get("bookmaker_name") or initial_house)
            physical = True
    return {
        "sport": "football",
        "fixture_id": fixture_id,
        "match": row.get("match"),
        "league_id": str(row.get("league_id") or row.get("league") or ""),
        "market": "Más de 2.5 goles",
        "market_key": MARKET_KEY,
        "selection_key": SELECTION_KEY,
        "p_matrix": p,
        "house": initial_house,
        "odds": initial_odds,
        "ev": initial_ev,
        "kickoff": kickoff,
        "source": str(path),
        "source_priority": 10,
        "physical_quote_verified": physical,
        "eligible_green": True,
        "watch_candidate": True,
        "execution": None,
    }


def shadow_ev_candidate(row: dict[str, Any], path: Path) -> dict[str, Any] | None:
    if str(row.get("decision") or "") != "BET_SHADOW":
        return None
    offer = row.get("best_policy_offer")
    if not isinstance(offer, dict):
        return None
    try:
        p = float(row.get("p_over_2_5"))
    except Exception:
        return None
    dec = odd(offer.get("decimal_odds"))
    if dec is None:
        return None
    ev = float(offer.get("ev") if offer.get("ev") is not None else p * dec - 1.0)
    return {
        "sport": "football",
        "fixture_id": str(row.get("fixture_id") or ""),
        "match": row.get("match"),
        "league_id": str(row.get("league_id") or row.get("league") or ""),
        "market": "Más de 2.5 goles",
        "market_key": MARKET_KEY,
        "selection_key": SELECTION_KEY,
        "p_matrix": p,
        "house": str(offer.get("bookmaker_name") or "Casa de política"),
        "odds": dec,
        "ev": ev,
        "kickoff": row.get("kickoff_utc"),
        "source": str(path),
        "source_priority": 10,
        "physical_quote_verified": True,
        "eligible_green": True,
        "execution": None,
    }


def discover_football(dates: list[str]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    governance_ok, governance = over25_signal_governance_authorized()
    if not governance_ok:
        return found
    for date in dates:
        root = FOOTBALL_ROOT / date
        if not root.exists():
            continue
        patterns = [
            ("browser_physical_verification/*.json", "browser"),
            ("shadow_quote_freeze/*.json", "freeze"),
            ("over25_shadow_ev/*.json", "shadow"),
        ]
        for pattern, kind in patterns:
            for path in sorted(root.glob(pattern)):
                try:
                    payload = load_json(path, {})
                except Exception:
                    continue
                if kind == "browser":
                    rows = payload.get("rows", [])
                    parser = browser_candidate
                elif kind == "freeze":
                    rows = payload.get("rows", [])
                    parser = quote_freeze_candidate
                else:
                    # Forward-only fail-closed rule: shadow EV rows are eligible for Telegram
                    # only when the market-scoped Over 2.5 promotion is still authoritative.
                    if payload.get("signal_generation_authorized") is not True:
                        continue
                    if payload.get("market_governance_status") != "PASS_PROMOTED_GOVERNED_P_MATRIX_SIGNAL_ONLY":
                        continue
                    if payload.get("probability_status") != "FROZEN_GOVERNED_MARKET_SCOPED_SIGNAL_ONLY":
                        continue
                    # Discovery must start from every scored P_MATRIX row that
                    # can still pass the immutable >=60% quality gate. Requiring
                    # BET_SHADOW here would discard fixtures merely because an
                    # executable quote was absent hours before kickoff. Exact
                    # authorized-book price and EV are enforced later inside the
                    # final 120-minute revalidation window.
                    rows = payload.get("all_rows", [])
                    parser = shadow_watch_candidate
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    candidate = parser(row, path)
                    if candidate is None or not candidate["fixture_id"]:
                        continue
                    key = signal_key(candidate["fixture_id"], candidate["market_key"], candidate["selection_key"])
                    candidate["signal_key"] = key
                    previous = found.get(key)
                    if previous is None or int(candidate["source_priority"]) > int(previous["source_priority"]):
                        found[key] = candidate
    return found


def discover_tennis(dates: list[str]) -> dict[str, dict[str, Any]]:
    # Fail closed: no canonical file, no validated lane, no physical quote or no positive EV => no alert.
    found: dict[str, dict[str, Any]] = {}
    valid_governance = {"VALIDATED", "STRONG", "PROMOTED"}
    for date in dates:
        root = TENNIS_ROOT / date
        if not root.exists():
            continue
        for path in sorted(root.glob("*.json")):
            try:
                payload = load_json(path, {})
            except Exception:
                continue
            rows = payload.get("rows", [])
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("governance_status") or "").upper() not in valid_governance:
                    continue
                if row.get("physical_quote_verified") is not True:
                    continue
                try:
                    p = float(row["p_matrix"])
                    dec = float(row["decimal_odds"])
                    ev = float(row["ev"])
                except Exception:
                    continue
                if dec <= 1.50 or ev <= 0:
                    continue
                event_id = str(row.get("event_id") or row.get("fixture_id") or "")
                market = str(row.get("market") or "")
                selection = str(row.get("selection") or "")
                if not event_id or not market or not selection:
                    continue
                key = hashlib.sha256(f"tennis|{event_id}|{market}|{selection}".encode("utf-8")).hexdigest()
                found[key] = {
                    "sport": "tennis",
                    "fixture_id": event_id,
                    "match": row.get("match"),
                    "market": market,
                    "market_key": market,
                    "selection_key": selection,
                    "p_matrix": p,
                    "house": str(row.get("house") or "Casa físicamente verificada"),
                    "odds": dec,
                    "ev": ev,
                    "kickoff": row.get("kickoff_bogota") or row.get("kickoff_utc"),
                    "source": str(path),
                    "source_priority": 30,
                    "physical_quote_verified": True,
                    "eligible_green": True,
                    "execution": None,
                    "signal_key": key,
                }
    return found


IDENTITY_TOKEN_ALIASES = {
    "utd": "united",
}


def _identity_norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    tokens = [IDENTITY_TOKEN_ALIASES.get(tok, tok) for tok in text.split()]
    return " ".join(tokens)


IDENTITY_CLUB_DESIGNATORS = {"fc", "sc", "cs", "csl", "afc", "cf", "club"}

def _identity_core_tokens(value: Any) -> list[str]:
    return [tok for tok in _identity_norm(value).split() if tok not in IDENTITY_CLUB_DESIGNATORS]

def _identity_similarity(left: Any, right: Any) -> float:
    a, b = _identity_norm(left), _identity_norm(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, a, b).ratio()
    subset = 1.0 if ta <= tb or tb <= ta else 0.0

    ca, cb = _identity_core_tokens(left), _identity_core_tokens(right)
    core_score = 0.0
    if ca and cb:
        core_a, core_b = " ".join(ca), " ".join(cb)
        if core_a == core_b:
            core_score = 1.0
        else:
            cta, ctb = set(ca), set(cb)
            core_jac = len(cta & ctb) / max(1, len(cta | ctb))
            core_seq = SequenceMatcher(None, core_a, core_b).ratio()
            core_subset = 1.0 if cta <= ctb or ctb <= cta else 0.0

            shorter, longer = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
            fuzzy_cover = 0.0
            if shorter and any(len(tok) >= 5 for tok in shorter):
                token_scores = [
                    max(SequenceMatcher(None, tok, other).ratio() for other in longer)
                    for tok in shorter
                ]
                if token_scores and min(token_scores) >= 0.90:
                    fuzzy_cover = sum(token_scores) / len(token_scores)
            core_score = max(core_jac, core_seq, core_subset, fuzzy_cover)
    return max(jac, seq, subset, core_score)


def odds_api_net_exact_over25_offer(
    session: requests.Session,
    odds_api_key: str,
    fixture_id: str,
    kickoff: Any,
    p: float,
    api_football_key: str,
    diagnostic: dict[str, Any] | None = None,
    required_house_key: str | None = None,
) -> dict[str, Any] | None:
    key = str(odds_api_key or "").strip()
    kickoff_dt = parse_dt(kickoff)
    if diagnostic is not None:
        diagnostic.clear()
        diagnostic.update({
            "fixture_id": str(fixture_id),
            "authorized_books": sorted(POLICY_BOOKS),
            "status": "STARTED",
            "rows_seen": 0,
            "rows_by_book": {},
            "candidate_lines_by_book": {},
            "discard_reasons": {},
            "sharp_reference_requested": ["pinnacle", "circa"],
            "sharp_reference_supported_but_not_requested": ["betfair"],
            "betfair_status": "PENDING_SEPARATE_EXCHANGE_FEED_PHYSICAL_VALIDATION",
            "market_context_requested": ["fanduel"],
            "sharp_quote_rows": [],
            "event_search_window_seconds": ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS,
        })
    if not key or kickoff_dt is None:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_CREDENTIAL_OR_KICKOFF"
        return None
    fr = session.get(
        "https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key": api_football_key},
        params={"id": fixture_id},
        timeout=20,
    )
    try:
        fp = fr.json()
    except Exception:
        return None
    rows = fp.get("response", []) if isinstance(fp, dict) else []
    if fr.status_code >= 300 or not rows:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_FIXTURE_LOOKUP"
        return None
    row = rows[0]
    home = str(((row.get("teams") or {}).get("home") or {}).get("name") or "")
    away = str(((row.get("teams") or {}).get("away") or {}).get("name") or "")
    start = int(kickoff_dt.timestamp())
    er = session.get(
        ODDS_API_NET_BASE + "/events",
        headers={"X-API-Key": key, "Accept": "application/json"},
        params={
            "sport": "soccer",
            "start_from": start - ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS,
            "start_to": start + ODDS_API_NET_EVENT_SEARCH_WINDOW_SECONDS,
            "limit": 100,
            "include_bookmaker_ids": "true",
        },
        timeout=20,
    )
    try:
        ep = er.json()
    except Exception:
        return None
    events = ep.get("items", []) if isinstance(ep, dict) else []
    scored: list[tuple[float, bool, dict[str, Any]]] = []
    for event in events or []:
        if not isinstance(event, dict):
            continue
        direct = (_identity_similarity(home, event.get("home_team")) + _identity_similarity(away, event.get("away_team"))) / 2.0
        swapped = (_identity_similarity(home, event.get("away_team")) + _identity_similarity(away, event.get("home_team"))) / 2.0
        scored.append((max(direct, swapped), direct >= swapped, event))
    scored.sort(key=lambda x: x[0], reverse=True)
    if diagnostic is not None:
        diagnostic["identity_source"] = {"home": home, "away": away, "kickoff": kickoff_dt.isoformat()}
        diagnostic["identity_top_scores"] = [round(float(x[0]), 6) for x in scored[:3]]
        diagnostic["identity_top_candidates"] = [
            {
                "score": round(float(score), 6),
                "orientation": "direct" if is_direct else "swapped",
                "event_id": str(event.get("event_id") or ""),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "start_time": event.get("start_time"),
                "home_similarity_direct": round(_identity_similarity(home, event.get("home_team")), 6),
                "away_similarity_direct": round(_identity_similarity(away, event.get("away_team")), 6),
                "home_similarity_swapped": round(_identity_similarity(home, event.get("away_team")), 6),
                "away_similarity_swapped": round(_identity_similarity(away, event.get("home_team")), 6),
            }
            for score, is_direct, event in scored[:5]
        ]
    if not scored:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_EVENT_NOT_COVERED"
        return None
    if scored[0][0] < 0.85:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_IDENTITY_LOW_SCORE"
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.05:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_IDENTITY_AMBIGUOUS"
        return None
    event_id = str(scored[0][2].get("event_id") or "")
    if not event_id:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_EVENT_ID_MISSING"
        return None
    if diagnostic is not None:
        diagnostic["odds_api_event_id"] = event_id
    sr = session.get(
        ODDS_API_NET_BASE + f"/events/{event_id}/odds/snapshot",
        headers={"X-API-Key": key, "Accept": "application/json"},
        params={
            "bookmakers": "betano,betplay,rushbet,pinnacle,circa,fanduel",
            "types": "total",
            "periods": "full time",
            "include_source": "true",
            "include_unavailable": "true",
        },
        timeout=20,
    )
    try:
        sp = sr.json()
    except Exception:
        return None
    if diagnostic is not None:
        diagnostic["snapshot_http_status"] = int(sr.status_code)
        diagnostic["snapshot_complete"] = sp.get("complete") if isinstance(sp, dict) else None
        diagnostic["excluded_bookmakers"] = sp.get("excluded_bookmakers") if isinstance(sp, dict) else None
    if sr.status_code >= 300 or not isinstance(sp, dict):
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_SNAPSHOT_PROVIDER_ERROR"
        return None
    book_ts = sp.get("bookmaker_as_of_ts_ms") or {}
    offers: list[dict[str, Any]] = []
    for item in sp.get("items") or []:
        if not isinstance(item, dict):
            continue
        house_key = str(item.get("bookmaker") or "").strip().casefold()
        if diagnostic is not None:
            diagnostic["rows_seen"] += 1
            diagnostic["rows_by_book"][house_key or "UNKNOWN"] = diagnostic["rows_by_book"].get(house_key or "UNKNOWN", 0) + 1
        if house_key not in POLICY_BOOKS and house_key not in REFERENCE_BOOKS:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["UNAUTHORIZED_BOOK"] = diagnostic["discard_reasons"].get("UNAUTHORIZED_BOOK", 0) + 1
            continue
        if house_key in POLICY_BOOKS and required_house_key and house_key != required_house_key:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["DIFFERENT_AUTHORIZED_BOOK"] = diagnostic["discard_reasons"].get("DIFFERENT_AUTHORIZED_BOOK", 0) + 1
            continue
        if item.get("is_available") is False:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["UNAVAILABLE"] = diagnostic["discard_reasons"].get("UNAVAILABLE", 0) + 1
            continue
        line_raw = item.get("line")
        try:
            dec = float(item.get("odds"))
        except (TypeError, ValueError):
            dec = None
        try:
            line = float(line_raw)
        except (TypeError, ValueError):
            m = re.search(r"(?:over|under)\s*([0-9]+(?:\.[0-9]+)?)", str(line_raw or "").casefold())
            line = float(m.group(1)) if m else None
        if line is None or dec is None:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["INVALID_LINE_OR_ODDS"] = diagnostic["discard_reasons"].get("INVALID_LINE_OR_ODDS", 0) + 1
                samples = diagnostic.setdefault("invalid_line_or_odds_samples", [])
                if len(samples) < 8:
                    samples.append({
                        "bookmaker": item.get("bookmaker"),
                        "market_key": item.get("market_key"),
                        "bet_type": item.get("bet_type"),
                        "metric": item.get("metric"),
                        "period": item.get("period"),
                        "period_str": item.get("period_str"),
                        "line": item.get("line"),
                        "side": item.get("side"),
                        "selection_name": item.get("selection_name"),
                        "odds": item.get("odds"),
                        "price": item.get("price"),
                        "decimal_odds": item.get("decimal_odds"),
                        "value": item.get("value"),
                        "raw_keys": sorted(item.keys()),
                    })
            continue
        if diagnostic is not None:
            diagnostic["candidate_lines_by_book"].setdefault(house_key, []).append({
                "market_key": item.get("market_key"),
                "bet_type": item.get("bet_type"),
                "metric": item.get("metric"),
                "period": item.get("period"),
                "period_str": item.get("period_str"),
                "line": item.get("line"),
                "side": item.get("side"),
                "selection_name": item.get("selection_name"),
                "odds": item.get("odds"),
            })

        if diagnostic is not None and house_key in {"pinnacle", "circa", "betfair", "fanduel"}:
            market_text_ref = " ".join([
                _identity_norm(item.get("market_key")),
                _identity_norm(item.get("bet_type")),
            ])
            label_ref = " ".join([
                _identity_norm(item.get("side")),
                _identity_norm(item.get("selection_name")),
                _identity_norm(item.get("selection_key")),
                _identity_norm(item.get("market_key")),
            ])
            if line == 2.5 and dec is not None and dec > 1.0 and (
                "total" in market_text_ref or "over under" in market_text_ref
            ):
                side_ref = "over" if "over" in label_ref else ("under" if "under" in label_ref else None)
                if side_ref:
                    ts_ms_ref = book_ts.get(house_key)
                    age_seconds_ref = None
                    if isinstance(ts_ms_ref, (int, float)) and not isinstance(ts_ms_ref, bool):
                        quote_dt_ref = datetime.fromtimestamp(float(ts_ms_ref) / 1000.0, tz=timezone.utc)
                        age_seconds_ref = max(0, int((now_utc() - quote_dt_ref).total_seconds()))
                    diagnostic["sharp_quote_rows"].append({
                        "source": house_key,
                        "side": side_ref,
                        "odds": dec,
                        "quote_age_seconds": age_seconds_ref,
                    })
        if house_key not in POLICY_BOOKS:
            continue
        if line != 2.5:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["LINE_NOT_2_5"] = diagnostic["discard_reasons"].get("LINE_NOT_2_5", 0) + 1
            continue
        if dec <= 1.50:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["ODDS_NOT_GT_1_50"] = diagnostic["discard_reasons"].get("ODDS_NOT_GT_1_50", 0) + 1
            continue
        market_text = " ".join([
            _identity_norm(item.get("market_key")),
            _identity_norm(item.get("bet_type")),
        ])
        if "total" not in market_text and "over under" not in market_text:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["NOT_TOTAL_MARKET"] = diagnostic["discard_reasons"].get("NOT_TOTAL_MARKET", 0) + 1
            continue
        label = " ".join([
            _identity_norm(item.get("side")),
            _identity_norm(item.get("selection_name")),
            _identity_norm(item.get("line")),
            _identity_norm(item.get("selection_key")),
            _identity_norm(item.get("market_key")),
        ])
        if "over" not in label:
            if diagnostic is not None:
                diagnostic["discard_reasons"]["NOT_OVER_SIDE"] = diagnostic["discard_reasons"].get("NOT_OVER_SIDE", 0) + 1
            continue
        ts_ms = book_ts.get(house_key)
        provider_updated = None
        if isinstance(ts_ms, (int, float)) and not isinstance(ts_ms, bool):
            provider_updated = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).isoformat()
        offers.append({
            "house": POLICY_BOOKS[house_key][0].replace("rush bet", "Rushbet").title() if house_key != "betplay" else "BetPlay",
            "house_key": house_key,
            "odds": dec,
            "ev": p * dec - 1.0,
            "break_even_probability": 1.0 / dec,
            "provider_quote_updated_at_utc": provider_updated,
            "provider": "odds-api.net",
            "fallback_multi_book": True,
            "odds_api_event_id": event_id,
        })
    if diagnostic is not None:
        paired: dict[str, dict[str, Any]] = {}
        for row_ref in diagnostic.get("sharp_quote_rows", []):
            src = str(row_ref.get("source") or "")
            side = str(row_ref.get("side") or "")
            if src and side in {"over", "under"}:
                paired.setdefault(src, {})[side] = row_ref
        consensus_inputs = []
        for src, sides in paired.items():
            if "over" in sides and "under" in sides:
                ages = [x.get("quote_age_seconds") for x in (sides["over"], sides["under"]) if x.get("quote_age_seconds") is not None]
                consensus_inputs.append({
                    "source": src,
                    "over_odds": float(sides["over"]["odds"]),
                    "under_odds": float(sides["under"]["odds"]),
                    "quote_age_seconds": max(ages) if ages else None,
                })
        diagnostic["sharp_consensus"] = assess_sharp_consensus(
            p_matrix=float(p),
            quotes=consensus_inputs,
        )
        diagnostic["eligible_offer_count"] = len(offers)
        diagnostic["status"] = "PASS_EXACT_OVER25_FOUND" if offers else "NO_EXACT_OVER25_FOUND"
    return max(offers, key=lambda x: x["ev"]) if offers else None


def _recompute_sharp_consensus(diagnostic: dict[str, Any], p: float) -> None:
    paired: dict[str, dict[str, Any]] = {}
    for row in diagnostic.get("sharp_quote_rows", []) or []:
        if not isinstance(row, Mapping):
            continue
        src = str(row.get("source") or "").strip().casefold()
        side = str(row.get("side") or "").strip().casefold()
        if src and side in {"over", "under"}:
            paired.setdefault(src, {})[side] = dict(row)
    consensus_inputs: list[dict[str, Any]] = []
    for src, sides in paired.items():
        if "over" not in sides or "under" not in sides:
            continue
        ages = [
            x.get("quote_age_seconds")
            for x in (sides["over"], sides["under"])
            if x.get("quote_age_seconds") is not None
        ]
        consensus_inputs.append({
            "source": src,
            "over_odds": float(sides["over"]["odds"]),
            "under_odds": float(sides["under"]["odds"]),
            "quote_age_seconds": max(ages) if ages else None,
        })
    diagnostic["sharp_consensus"] = assess_sharp_consensus(
        p_matrix=float(p),
        quotes=consensus_inputs,
    )


def api_football_pinnacle_over25_reference(
    session: requests.Session,
    api_key: str,
    fixture_id: str,
    p: float,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fallback sharp transport using API-Football Pinnacle bookmaker_id=4.

    This mirrors the CLV transport contract: Pinnacle is reference-only,
    never mutates P_MATRIX, and must be complete and <=120 seconds old.
    """
    key = str(api_key or "").strip()
    if diagnostic is not None:
        diagnostic.clear()
        diagnostic.update({
            "transport": "API-Football /odds bookmaker_id=4",
            "fixture_id": str(fixture_id),
            "reference_bookmaker": "Pinnacle",
            "bookmaker_id": 4,
            "strict_fresh_gate_seconds": 120,
            "status": "STARTED",
            "p_matrix_mutated_by_odds": False,
            "real_money": "BLOCKED",
        })
    if not key:
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_CREDENTIAL_MISSING"
        return None
    response = session.get(
        "https://v3.football.api-sports.io/odds",
        headers={"x-apisports-key": key},
        params={"fixture": str(fixture_id), "bookmaker": 4},
        timeout=20,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if diagnostic is not None:
        diagnostic["http_status"] = int(response.status_code)
    if response.status_code >= 300 or not isinstance(payload, Mapping):
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_PROVIDER_ERROR"
        return None

    for fixture_row in payload.get("response", []) or []:
        if not isinstance(fixture_row, Mapping):
            continue
        provider_update = parse_dt(fixture_row.get("update"))
        if provider_update is None:
            continue
        for bookmaker in fixture_row.get("bookmakers", []) or []:
            if not isinstance(bookmaker, Mapping):
                continue
            if str(bookmaker.get("id")) != "4":
                continue
            if str(bookmaker.get("name") or "").strip().casefold() != "pinnacle":
                continue
            for bet in bookmaker.get("bets", []) or []:
                if not isinstance(bet, Mapping):
                    continue
                try:
                    bet_id = int(bet.get("id"))
                except Exception:
                    continue
                if bet_id != 5 or str(bet.get("name") or "").strip().casefold() != "goals over/under":
                    continue
                over = under = None
                for value in bet.get("values", []) or []:
                    if not isinstance(value, Mapping):
                        continue
                    label = str(value.get("value") or "").strip().casefold()
                    dec = odd(value.get("odd"))
                    if dec is None:
                        continue
                    if label == "over 2.5":
                        over = dec
                    elif label == "under 2.5":
                        under = dec
                if over is None or under is None:
                    continue
                age_seconds = int((now_utc() - provider_update).total_seconds())
                if diagnostic is not None:
                    diagnostic.update({
                        "provider_quote_updated_at_utc": provider_update.isoformat(),
                        "provider_quote_age_seconds": age_seconds,
                        "over_2_5_decimal_odds": over,
                        "under_2_5_decimal_odds": under,
                    })
                if age_seconds < 0 or age_seconds > 120:
                    if diagnostic is not None:
                        diagnostic["status"] = "BLOCKED_STALE_PINNACLE_REFERENCE"
                    return None
                row = {
                    "source": "pinnacle",
                    "over_odds": over,
                    "under_odds": under,
                    "quote_age_seconds": age_seconds,
                }
                if diagnostic is not None:
                    diagnostic["status"] = "PASS_FRESH_PINNACLE_REFERENCE"
                return row

    if diagnostic is not None:
        diagnostic["status"] = "BLOCKED_PINNACLE_OVER25_MARKET_INCOMPLETE"
    return None


def augment_sharp_diagnostic_with_api_football_fallback(
    diagnostic: dict[str, Any],
    *,
    session: requests.Session,
    api_key: str,
    fixture_id: str,
    p: float,
) -> dict[str, Any]:
    """Add API-Football Pinnacle only when odds-api.net lacks a fresh Pinnacle."""
    state, _ = sharp_reference_gate_state(diagnostic)
    if state != "BLOCKED_NO_FRESH_PINNACLE_REFERENCE":
        diagnostic["api_football_pinnacle_fallback"] = {
            "status": "NOT_NEEDED_PRIMARY_PINNACLE_AVAILABLE"
        }
        return diagnostic
    fallback_diag: dict[str, Any] = {}
    row = api_football_pinnacle_over25_reference(
        session,
        api_key,
        fixture_id,
        p,
        fallback_diag,
    )
    diagnostic["api_football_pinnacle_fallback"] = fallback_diag
    if row is None:
        return diagnostic
    diagnostic.setdefault("sharp_quote_rows", []).extend([
        {
            "source": "pinnacle",
            "side": "over",
            "odds": row["over_odds"],
            "quote_age_seconds": row["quote_age_seconds"],
            "transport": "api-football",
        },
        {
            "source": "pinnacle",
            "side": "under",
            "odds": row["under_odds"],
            "quote_age_seconds": row["quote_age_seconds"],
            "transport": "api-football",
        },
    ])
    _recompute_sharp_consensus(diagnostic, p)
    return diagnostic


def sharp_reference_gate_state(diagnostic: Mapping[str, Any] | None) -> tuple[str, dict[str, Any]]:
    """Require a fresh Pinnacle reference before a football green signal.

    Circa and Betfair may corroborate the primary reference. FanDuel is
    context-only and never satisfies the sharp gate. The sharp market never
    mutates P_MATRIX; it only approves or blocks downstream signal emission.
    """
    diag = diagnostic if isinstance(diagnostic, Mapping) else {}
    raw = diag.get("sharp_consensus")
    consensus = raw if isinstance(raw, Mapping) else {}
    sharp_rows = consensus.get("sharp_rows")
    if not isinstance(sharp_rows, list):
        sharp_rows = []
    fresh_sources = {
        str(row.get("source") or "").strip().casefold().replace(" ", "")
        for row in sharp_rows
        if isinstance(row, Mapping)
    }
    pinnacle_present = "pinnacle" in fresh_sources
    status = str(consensus.get("status") or "INSUFFICIENT_SHARP_COVERAGE")
    detail = {
        "policy": "PINNACLE_PRIMARY_SHARP_GATE_V1",
        "consensus_status": status,
        "fresh_sharp_sources": sorted(fresh_sources),
        "pinnacle_present": pinnacle_present,
        "circa_present": "circa" in fresh_sources,
        "betfair_present": "betfair" in fresh_sources,
        "fanduel_counts_as_sharp": False,
        "p_matrix_mutated_by_odds": False,
        "real_money": "BLOCKED",
    }
    if not pinnacle_present:
        return "BLOCKED_NO_FRESH_PINNACLE_REFERENCE", detail
    if status == "CONTRADICTION_REVIEW":
        return "BLOCKED_SHARP_CONTRADICTION", detail
    if status in {"PASS_ALIGNED", "SINGLE_SHARP_REFERENCE_ONLY"}:
        return "PASS_SHARP_REFERENCE_GATE", detail
    return "BLOCKED_INSUFFICIENT_SHARP_COVERAGE", detail


def physical_book_over25_offer(
    fixture_id: str,
    p: float,
    now: datetime,
    *,
    required_house_key: str | None = None,
    root: Path = PHYSICAL_BOOK_QUOTE_ROOT,
) -> dict[str, Any] | None:
    """Load the freshest physically captured authorized-book Over 2.5 quote.

    Fail closed unless fixture identity, market, house, odds, freshness and
    prematch timing are all explicit in the evidence artifact.
    """
    best: dict[str, Any] | None = None
    target_fixture = str(fixture_id)
    if not root.exists():
        return None
    for path in root.glob("*/MATRIX_*_QUOTE_*.json"):
        data = load_json(path, {})
        if not isinstance(data, dict):
            continue
        if data.get("schema") != "MATRIX_PHYSICAL_BOOK_QUOTE_V1":
            continue
        if str(data.get("fixture_id") or "") != target_fixture:
            continue
        if str(data.get("market") or "").strip().casefold() not in {
            "más de 2.5 goles",
            "mas de 2.5 goles",
            "over 2.5",
        }:
            continue
        house_key = bookmaker_key(data.get("house"))
        if house_key is None:
            continue
        if required_house_key is not None and house_key != required_house_key:
            continue
        dec = odd(data.get("decimal_odds"))
        if dec is None or dec <= 1.50:
            continue
        captured = parse_dt(data.get("captured_at_utc") or data.get("captured_at_bogota"))
        kickoff = parse_dt(data.get("kickoff_utc"))
        if captured is None or kickoff is None:
            continue
        age_seconds = (now - captured).total_seconds()
        if age_seconds < 0 or age_seconds > PHYSICAL_BOOK_QUOTE_MAX_AGE_MINUTES * 60:
            continue
        if captured >= kickoff or now >= kickoff:
            continue
        offer = {
            "house": str(data.get("house") or ""),
            "house_key": house_key,
            "odds": dec,
            "ev": p * dec - 1.0,
            "break_even_probability": 1.0 / dec,
            "provider_quote_updated_at_utc": captured.isoformat(),
            "provider": "physical-browser-evidence",
            "physical_evidence_path": str(path),
            "fallback_multi_book": True,
        }
        if best is None or parse_dt(offer["provider_quote_updated_at_utc"]) > parse_dt(best["provider_quote_updated_at_utc"]):
            best = offer
    return best


def exact_over25_offer(
    session: requests.Session,
    api_key: str,
    fixture_id: str,
    p: float,
    required_house_key: str | None = None,
    diagnostic: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if diagnostic is not None:
        diagnostic.clear()
        diagnostic.update({
            "provider": "API-Football",
            "fixture_id": str(fixture_id),
            "required_house_key": required_house_key,
            "authorized_books_seen": [],
            "goals_over_under_books": [],
            "over25_books": [],
            "eligible_offer_count": 0,
            "status": "STARTED",
        })
    response = session.get(
        "https://v3.football.api-sports.io/odds",
        headers={"x-apisports-key": api_key},
        params={"fixture": fixture_id},
        timeout=20,
    )
    try:
        payload = response.json()
    except Exception:
        payload = {}
    if diagnostic is not None:
        diagnostic["http_status"] = int(response.status_code)
        diagnostic["response_rows"] = len(payload.get("response", []) or []) if isinstance(payload, dict) else 0
    if response.status_code >= 300 or (isinstance(payload, dict) and payload.get("errors") not in ({}, [], None)):
        if diagnostic is not None:
            diagnostic["status"] = "BLOCKED_PROVIDER_ERROR"
        return None
    offers: list[dict[str, Any]] = []
    for fr in payload.get("response", []) or []:
        if not isinstance(fr, dict):
            continue
        for book in fr.get("bookmakers", []) or []:
            if not isinstance(book, dict):
                continue
            bk = bookmaker_key(book.get("name"))
            if bk is None:
                continue
            if diagnostic is not None and bk not in diagnostic["authorized_books_seen"]:
                diagnostic["authorized_books_seen"].append(bk)
            if required_house_key is not None and bk != required_house_key:
                continue
            for bet in book.get("bets", []) or []:
                if not isinstance(bet, dict):
                    continue
                try:
                    bid = int(bet.get("id"))
                except Exception:
                    continue
                if bid != 5 or str(bet.get("name") or "").strip().casefold() != "goals over/under":
                    continue
                if diagnostic is not None and bk not in diagnostic["goals_over_under_books"]:
                    diagnostic["goals_over_under_books"].append(bk)
                for value in bet.get("values", []) or []:
                    if not isinstance(value, dict) or str(value.get("value") or "").strip().casefold() != "over 2.5":
                        continue
                    if diagnostic is not None and bk not in diagnostic["over25_books"]:
                        diagnostic["over25_books"].append(bk)
                    dec = odd(value.get("odd"))
                    if dec is None or dec <= 1.50:
                        continue
                    offers.append({
                        "house": str(book.get("name") or ""),
                        "odds": dec,
                        "ev": p * dec - 1.0,
                        "break_even_probability": 1.0 / dec,
                        "provider_quote_updated_at_utc": fr.get("update"),
                    })
    if diagnostic is not None:
        diagnostic["eligible_offer_count"] = len(offers)
        if offers:
            diagnostic["status"] = "PASS_EXACT_AUTHORIZED_OVER25_FOUND"
        elif not diagnostic.get("authorized_books_seen"):
            diagnostic["status"] = "BLOCKED_NO_AUTHORIZED_BOOK_COVERAGE"
        elif not diagnostic.get("goals_over_under_books"):
            diagnostic["status"] = "BLOCKED_AUTHORIZED_BOOK_NO_TOTALS_MARKET"
        elif not diagnostic.get("over25_books"):
            diagnostic["status"] = "BLOCKED_AUTHORIZED_BOOK_NO_OVER25_LINE"
        else:
            diagnostic["status"] = "BLOCKED_AUTHORIZED_BOOK_OVER25_ODDS_NOT_GT_1_50"
    return max(offers, key=lambda x: x["ev"]) if offers else None

def fixture_final(session: requests.Session, api_key: str, fixture_id: str) -> dict[str, Any] | None:
    response = session.get(
        "https://v3.football.api-sports.io/fixtures",
        headers={"x-apisports-key": api_key},
        params={"id": fixture_id},
        timeout=20,
    )
    try:
        payload = response.json()
    except Exception:
        return None
    if response.status_code >= 300 or payload.get("errors") not in ({}, [], None):
        return None
    rows = payload.get("response", []) or []
    if not rows:
        return None
    row = rows[0]
    status = str(((row.get("fixture") or {}).get("status") or {}).get("short") or "").upper()
    if status not in FINAL_STATUSES:
        return {"final": False, "status": status}
    goals = row.get("goals") or {}
    hg, ag = goals.get("home"), goals.get("away")
    if not isinstance(hg, int) or not isinstance(ag, int):
        return None
    return {
        "final": True,
        "status": status,
        "home_goals": hg,
        "away_goals": ag,
    }


def fmt_cop(value: float) -> str:
    return f'{int(round(float(value))):,}'.replace(",", ".")


def paper_stake_level(c: dict[str, Any]) -> int:
    """Return the governed paper stake after the temporary risk cap.

    The confidence tiers are intentionally not used to increase exposure while
    the 17-OCT physical audit shows material overconfidence in the high-EV tail.
    Signal-generation gates and P_MATRIX remain unchanged.
    """
    _ = float(c["p_matrix"])
    _ = float(c["ev"])
    return PAPER_STAKE_MAX_LEVEL


def paper_stake_cop(level: int) -> float:
    return PAPER_UNIT_COP * PAPER_STAKE_LEVELS[int(level)]


def paper_daily_cap_fraction(candidates_for_day: list[dict[str, Any]]) -> float:
    if PAPER_STAKE_MAX_LEVEL <= 1:
        return PAPER_DAILY_BASE_EXPOSURE_FRACTION
    eligible = [c for c in candidates_for_day if c.get("eligible_green") is True and float(c.get("ev") or 0.0) > 0.0]
    if not eligible:
        return PAPER_DAILY_BASE_EXPOSURE_FRACTION
    levels = [paper_stake_level(c) for c in eligible]
    stake3 = sum(1 for x in levels if x == 3)
    tier23 = sum(1 for x in levels if x >= 2)
    share = tier23 / len(levels)
    if stake3 >= PAPER_HIGH_CONF_MIN_STAKE3 and share >= PAPER_HIGH_CONF_MIN_TIER23_SHARE:
        return PAPER_DAILY_MAX_EXPOSURE_FRACTION
    return PAPER_DAILY_BASE_EXPOSURE_FRACTION


def paper_kickoff_date(value: Any) -> str | None:
    dt = parse_dt(value)
    return str(dt.astimezone(BOGOTA).date()) if dt is not None else None


def register_monitoring_breach(lifecycle: dict[str, Any], now: datetime) -> bool:
    """Record a monitoring breach once and freeze its first physical detection.

    Returns True only on the first transition into monitoring_breach=True so
    run-level telemetry does not recount the same historical breach forever.
    """
    already_recorded = lifecycle.get("monitoring_breach") is True
    lifecycle["monitoring_breach"] = True
    lifecycle.setdefault("monitoring_breach_detected_at_utc", now.isoformat())
    lifecycle.setdefault("first_terminal_state", "BLOCKED_KICKOFF_REACHED_MONITORING_BREACH")
    lifecycle.setdefault("first_terminal_at_utc", now.isoformat())
    return not already_recorded


def prematch_revalidation_state(candidate: dict[str, Any], now: datetime) -> str:
    kickoff = parse_dt(candidate.get("kickoff"))
    if kickoff is None:
        return "BLOCKED_INVALID_KICKOFF"
    seconds = (kickoff - now).total_seconds()
    if seconds <= 0:
        return "BLOCKED_KICKOFF_REACHED"
    if seconds > GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES * 60:
        return "WAITING_FINAL_REVALIDATION_WINDOW"
    return "READY_FOR_FINAL_REVALIDATION"


def final_prematch_quote_state(offer: dict[str, Any] | None) -> str:
    if offer is None:
        return "BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25"
    if float(offer.get("ev") or 0.0) <= 0:
        return "BLOCKED_NONPOSITIVE_EV"
    return "PASS_FINAL_PREMATCH_REVALIDATION"


def signal_quality_gate_state(candidate: dict[str, Any], offer: dict[str, Any]) -> str:
    p_matrix = float(candidate.get("p_matrix") or 0.0)
    revalidated_ev = float(offer.get("ev") or 0.0)
    if p_matrix < SIGNAL_QUALITY_MIN_P_MATRIX:
        return "BLOCKED_QUALITY_P_MATRIX_BELOW_60PCT"
    if revalidated_ev < SIGNAL_QUALITY_MIN_REVALIDATED_EV:
        return "BLOCKED_QUALITY_REVALIDATED_EV_BELOW_5PCT"
    return "PASS_API_COST_RECOVERY_PRECISION_GATE"


def paper_league_concentration_blocked(existing_count: int) -> bool:
    return int(existing_count) >= PAPER_MAX_SIGNALS_PER_LEAGUE_DAY


def paper_league_day_key(candidate: dict[str, Any]) -> tuple[str, str] | None:
    day = paper_kickoff_date(candidate.get("kickoff"))
    league_id = str(candidate.get("league_id") or "").strip()
    if not day or not league_id:
        return None
    return day, league_id


def paper_daily_exposure_by_date(ledger: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for record in ledger.get("sent", []):
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        status = str(bet.get("status") or "").upper()
        if status in {"CANCELLED_NO_BET", "VOID_POSTPONED"}:
            continue
        day = bet.get("kickoff_bogota_date") or paper_kickoff_date(record.get("kickoff"))
        if not day:
            continue
        out[str(day)] = out.get(str(day), 0.0) + float(bet.get("stake_cop") or 0.0)
    return out


def current_correlated_exposures(ledger: dict[str, Any]) -> list[ExposureRecord]:
    rows: list[ExposureRecord] = []
    for record in ledger.get("sent", []):
        if not isinstance(record, dict):
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        if str(bet.get("status") or "").upper() != "OPEN":
            continue
        stake = float(bet.get("stake_cop") or 0.0)
        day = str(bet.get("kickoff_bogota_date") or paper_kickoff_date(record.get("kickoff")) or "").strip()
        fixture_id = str(record.get("fixture_id") or "").strip()
        league_id = str(record.get("league_id") or "UNKNOWN").strip() or "UNKNOWN"
        if stake <= 0 or not day or not fixture_id:
            continue
        rows.append(ExposureRecord(fixture_id, league_id, day, stake))
    return rows


def correlated_risk_limits_from_physical_calibration(
    calibration: dict[str, Any],
    *,
    bankroll: float,
) -> CorrelationLimits:
    capital = float(bankroll)
    if capital <= 0:
        raise ValueError("BANKROLL_MUST_BE_POSITIVE")
    caps = calibration.get("caps") or {}
    fixture_cap_cop = float(caps.get("fixture_cap_cop") or 0.0)
    tournament_day_cap_cop = float(caps.get("tournament_day_cap_cop") or 0.0)
    day_cap_fraction = float(caps.get("daily_cap_fraction") or 0.0)
    if fixture_cap_cop <= 0 or tournament_day_cap_cop <= 0 or not 0 < day_cap_fraction <= 1:
        raise ValueError("PHYSICAL_CORRELATED_RISK_CAPS_INVALID")
    return CorrelationLimits(
        max_fixture_fraction=min(1.0, fixture_cap_cop / capital),
        max_tournament_day_fraction=min(1.0, tournament_day_cap_cop / capital),
        max_day_fraction=day_cap_fraction,
    )


def correlated_risk_gate_state(
    candidate: dict[str, Any],
    *,
    bankroll: float,
    limits: CorrelationLimits,
    existing: list[ExposureRecord],
) -> tuple[str, dict[str, Any], ExposureRecord | None]:
    day = paper_kickoff_date(candidate.get("kickoff"))
    fixture_id = str(candidate.get("fixture_id") or "").strip()
    league_id = str(candidate.get("league_id") or "UNKNOWN").strip() or "UNKNOWN"
    if not day or not fixture_id:
        return "BLOCKED_CORRELATED_RISK_IDENTITY_INCOMPLETE", {"allowed": False}, None
    proposed = ExposureRecord(
        fixture_id=fixture_id,
        tournament_key=league_id,
        operational_date=day,
        stake=PAPER_UNIT_COP,
    )
    decision = assess_correlated_exposure(
        existing,
        proposed,
        bankroll=float(bankroll),
        limits=limits,
    )
    detail = {
        "allowed": decision.allowed,
        "status": decision.status,
        "fixture_exposure_after_cop": decision.fixture_exposure_after,
        "tournament_day_exposure_after_cop": decision.tournament_day_exposure_after,
        "day_exposure_after_cop": decision.day_exposure_after,
        "blocked_reasons": list(decision.blocked_reasons),
        "limits": {
            "max_fixture_fraction": limits.max_fixture_fraction,
            "max_tournament_day_fraction": limits.max_tournament_day_fraction,
            "max_day_fraction": limits.max_day_fraction,
        },
        "paper_stake_cop": PAPER_UNIT_COP,
        "real_money": "BLOCKED",
    }
    return (
        "PASS_CORRELATED_EXPOSURE_GATE" if decision.allowed else "BLOCKED_CORRELATED_EXPOSURE",
        detail,
        proposed if decision.allowed else None,
    )


def reconcile_existing_paper_state(ledger: dict[str, Any], now: datetime) -> dict[str, int]:
    sent_by_key = {
        str(x.get("signal_key") or ""): x
        for x in ledger.get("sent", [])
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    settlement_by_key = {
        str(x.get("signal_key") or ""): x
        for x in ledger.get("settlements", [])
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    cancelled = 0
    backfilled = 0

    # A prematch NO_APOSTAR correction cancels the paper bet and releases its stake.
    for correction in ledger.get("corrections", []):
        if not isinstance(correction, dict) or correction.get("status") != "NO_APOSTAR_ENVIADO":
            continue
        key = str(correction.get("signal_key") or "")
        record = sent_by_key.get(key)
        if not isinstance(record, dict):
            continue
        correction_at = parse_dt(correction.get("sent_at_utc"))
        kickoff = parse_dt(record.get("kickoff"))
        if correction_at is None or kickoff is None or correction_at >= kickoff:
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        if str(bet.get("status") or "").upper() == "CANCELLED_NO_BET":
            continue
        bet["status"] = "CANCELLED_NO_BET"
        bet["cancelled_at_utc"] = correction_at.isoformat()
        bet["cancel_reason"] = "PREMATCH_NO_APOSTAR_CORRECTION"
        bet["profit_cop"] = 0.0
        settlement = settlement_by_key.get(key)
        if isinstance(settlement, dict):
            settlement["paper_reconciliation_status"] = "VOIDED_BY_PREMATCH_NO_APOSTAR_CORRECTION"
            settlement["paper_reconciliation_at_utc"] = now.isoformat()
            settlement["paper_profit_cop"] = 0.0
            settlement["paper_stake_cop"] = 0.0
            settlement["paper_stake_level"] = None
        cancelled += 1

    # Older FINAL rows can predate the paper-stake assignment. Reconcile them
    # deterministically from the frozen odds and the already-recorded outcome.
    for key, settlement in settlement_by_key.items():
        record = sent_by_key.get(key)
        if not isinstance(record, dict):
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict) or str(bet.get("status") or "").upper() != "OPEN":
            continue
        stake = float(bet.get("stake_cop") or 0.0)
        if stake <= 0:
            continue
        frozen_odds = float(record.get("odds") or settlement.get("odds") or 0.0)
        if frozen_odds <= 1.0:
            continue
        won = bool(settlement.get("won"))
        profit = stake * (frozen_odds - 1.0) if won else -stake
        bet["status"] = "SETTLED"
        bet["settled_at_utc"] = settlement.get("settled_at_utc") or now.isoformat()
        bet["profit_cop"] = profit
        bet["settlement_reconciled_from_existing_final"] = True
        settlement["paper_stake_level"] = int(bet.get("stake_level") or 0) or None
        settlement["paper_stake_cop"] = stake
        settlement["paper_profit_cop"] = profit
        settlement["paper_reconciliation_status"] = "BACKFILLED_FROM_EXISTING_FINAL_AND_FROZEN_ODDS"
        settlement["paper_reconciliation_at_utc"] = now.isoformat()
        backfilled += 1

    return {"cancelled_no_bet": cancelled, "settlement_backfills": backfilled}


def paper_exposure_policy_message(pb: dict[str, Any]) -> str:
    return "\n".join([
        "🔵 ACTUALIZACIÓN — EXPOSICIÓN DIARIA BANKROLL DE PAPEL",
        "",
        "Exposición diaria estándar: 30% del bankroll.",
        "Día de alta convicción: hasta 40% del bankroll.",
        f"Gate 40%: al menos {PAPER_HIGH_CONF_MIN_STAKE3} señales Stake 3 y >= {PAPER_HIGH_CONF_MIN_TIER23_SHARE*100:.0f}% de las señales del día en Stake 2/3.",
        "Si no cumple ambos gates, se mantiene 30%.",
        "La cohorte del 10-OCT cumple el gate de alta convicción y su 36% queda dentro del máximo 40%.",
        "Solo apuestas simples de papel. Sin dinero real.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])

def recalc_paper_bankroll(ledger: dict[str, Any]) -> dict[str, Any]:
    pb = ledger.setdefault("paper_bankroll", {})
    pb.setdefault("schema", "MATRIX_PAPER_BANKROLL_V1")
    pb.setdefault("status", "ACTIVE")
    pb.setdefault("currency", "COP")
    pb.setdefault("initial_cop", PAPER_BANKROLL_INITIAL_COP)
    pb.setdefault("unit_fraction_initial_bankroll", PAPER_UNIT_FRACTION)
    pb.setdefault("unit_cop", PAPER_UNIT_COP)
    pb.setdefault("stake_levels_cop", {
        "1": paper_stake_cop(1),
        "2": paper_stake_cop(2),
        "3": paper_stake_cop(3),
    })
    historical_policy = {
        "stake_3": "P_MATRIX >= 65% AND EV >= 10%",
        "stake_2": "P_MATRIX >= 60% AND EV >= 5%",
        "stake_1": "remaining eligible green signals with positive EV",
    }
    pb.setdefault("confidence_policy_historical", historical_policy)
    pb["confidence_policy"] = {
        "stake_1": "ACTIVE: all eligible paper signals capped at 1u / COP 25,000",
        "stake_2": "TEMPORARILY_DISABLED_BY_RISK_OVERRIDE",
        "stake_3": "TEMPORARILY_DISABLED_BY_RISK_OVERRIDE",
    }
    pb["stake_risk_override"] = {
        "status": "ACTIVE",
        "policy": PAPER_STAKE_RISK_OVERRIDE,
        "max_stake_level": PAPER_STAKE_MAX_LEVEL,
        "max_stake_cop": paper_stake_cop(PAPER_STAKE_MAX_LEVEL),
        "basis": "17-OCT physical loss audit: 2u/3u amplified high-P/high-EV overconfidence",
        "retirement_gate": "Do not restore 2u/3u until calibration/CLV evidence clears high-P/high-EV overconfidence.",
    }
    pb["max_open_exposure_fraction"] = PAPER_MAX_OPEN_EXPOSURE_FRACTION
    pb["daily_base_exposure_fraction"] = PAPER_DAILY_BASE_EXPOSURE_FRACTION
    pb["daily_max_exposure_fraction"] = PAPER_DAILY_MAX_EXPOSURE_FRACTION
    pb["effective_daily_cap_fraction_under_risk_override"] = PAPER_DAILY_BASE_EXPOSURE_FRACTION
    pb["high_confidence_day_gate"] = {
        "minimum_stake3_signals": PAPER_HIGH_CONF_MIN_STAKE3,
        "minimum_tier2_or_3_share": PAPER_HIGH_CONF_MIN_TIER23_SHARE,
    }
    pb.setdefault("singles_only", True)
    pb.setdefault("automatic_real_money_execution", False)
    # The canonical paper-bankroll source of truth is sent[].paper_bet.
    # Historical settlement entries can mirror the same result and must never be
    # summed independently, otherwise autonomous runs can double count or revert
    # externally reconciled PAPER closures.
    open_bets = []
    settled_bets = []
    settlements_by_key = {
        str(x.get("signal_key")): x
        for x in ledger.get("settlements", [])
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    realized = 0.0
    for record in ledger.get("sent", []):
        bet = record.get("paper_bet")
        if not isinstance(bet, dict):
            continue
        status = str(bet.get("status") or "").upper()
        if status == "OPEN":
            open_bets.append(bet)
            continue
        if status != "SETTLED":
            continue
        settled_bets.append(bet)
        profit = bet.get("profit_cop")
        if profit is None:
            legacy = settlements_by_key.get(str(record.get("signal_key") or ""))
            profit = None if legacy is None else legacy.get("paper_profit_cop")
        if profit is None:
            raise ValueError(
                f"SETTLED_PAPER_BET_MISSING_PROFIT:{record.get('signal_key') or record.get('fixture_id')}"
            )
        realized += float(profit)

    reconciliation_adjustment = sum(
        float(x.get("amount_cop") or 0.0)
        for x in ledger.get("paper_bankroll_adjustments", [])
        if isinstance(x, dict) and str(x.get("status") or "").upper() == "APPLIED"
    )
    current = float(pb["initial_cop"]) + reconciliation_adjustment + realized
    open_exposure = sum(float(x.get("stake_cop") or 0.0) for x in open_bets)
    pb["reconciliation_adjustment_cop"] = reconciliation_adjustment
    pb["realized_profit_cop"] = realized
    pb["current_cop"] = current
    pb["open_exposure_cop"] = open_exposure
    pb["available_after_open_exposure_cop"] = current - open_exposure
    pb["open_bets"] = len(open_bets)
    pb["settled_paper_bets"] = len(settled_bets)
    pb["max_open_exposure_cop"] = current * float(pb["max_open_exposure_fraction"])
    return pb


def paper_bankroll_balance_correction_message(pb: dict[str, Any]) -> str:
    return "\n".join([
        "🔵 CORRECCIÓN — BANKROLL DE PAPEL DISPONIBLE",
        "",
        f'Capital total de papel: COP {fmt_cop(pb.get("current_cop") or 0)}',
        f'Exposición actualmente comprometida: COP {fmt_cop(pb.get("open_exposure_cop") or 0)}',
        f'BANKROLL DISPONIBLE PARA NUEVAS SEÑALES: COP {fmt_cop(pb.get("available_after_open_exposure_cop") or 0)}',
        f'Apuestas de papel abiertas: {int(pb.get("open_bets") or 0)}',
        "La exposición abierta se descuenta del saldo disponible aunque el capital total solo cambia cuando hay settlements FINAL.",
        "Solo simulación de papel. Sin ejecución automática.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def paper_bankroll_activation_message(pb: dict[str, Any], assigned_now: int) -> str:
    return "\n".join([
        "🧪 BANKROLL DE PAPEL MATRIX ACTIVADO",
        "",
        f'Bankroll inicial: COP {fmt_cop(pb["initial_cop"])}',
        f'1 unidad: COP {fmt_cop(pb["unit_cop"])} (0,5% del bankroll inicial)',
        f'Stake operativo actual: STAKE 1 = COP {fmt_cop(pb["stake_levels_cop"]["1"])}',
        "Stake 2: TEMPORALMENTE DESHABILITADO por guardrail de riesgo",
        "Stake 3: TEMPORALMENTE DESHABILITADO por guardrail de riesgo",
        f'Política temporal: {pb.get("stake_risk_override", {}).get("policy") or PAPER_STAKE_RISK_OVERRIDE}',
        f'Stake máximo actual: {int(pb.get("stake_risk_override", {}).get("max_stake_level") or PAPER_STAKE_MAX_LEVEL)}u',
        f'Exposición diaria operativa bajo guardrail: {float(pb.get("effective_daily_cap_fraction_under_risk_override") or PAPER_DAILY_BASE_EXPOSURE_FRACTION)*100:.0f}%',
        f'Apuestas de papel asignadas ahora: {assigned_now}',
        "Solo apuestas simples. Sin dinero real.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def paper_full_cohort_message(pb: dict[str, Any]) -> str:
    cohort = pb.get("initial_cohort") or {}
    return "\n".join([
        "✅ COHORTE INICIAL DE 45 SEÑALES — BANKROLL DE PAPEL",
        "",
        f'Señales incluidas: {int(cohort.get("signal_count") or 0)}',
        f'Stake 1: {int(cohort.get("stake_1_count") or 0)} apuestas',
        f'Stake 2: {int(cohort.get("stake_2_count") or 0)} apuestas',
        f'Stake 3: {int(cohort.get("stake_3_count") or 0)} apuestas',
        f'Exposición de papel: COP {fmt_cop(cohort.get("exposure_cop") or 0)}',
        f'Bankroll inicial: COP {fmt_cop(pb.get("initial_cop") or 0)}',
        f'Saldo no comprometido: COP {fmt_cop(pb.get("available_after_open_exposure_cop") or 0)}',
        "La cohorte cumple el gate de día de alta convicción.",
        "Su exposición del 36% está dentro del máximo diario permitido del 40%.",
        "SOLO PAPEL — SIN DINERO REAL.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def paper_portfolio_messages(ledger: dict[str, Any]) -> list[str]:
    pb = recalc_paper_bankroll(ledger)
    rows = []
    for record in ledger.get("sent", []):
        bet = record.get("paper_bet")
        if not isinstance(bet, dict) or bet.get("status") != "OPEN":
            continue
        rows.append({
            "match": record.get("match"),
            "house": record.get("house"),
            "odds": record.get("odds"),
            "ev": record.get("ev"),
            "stake_level": bet.get("stake_level"),
            "stake_cop": bet.get("stake_cop"),
        })
    rows.sort(key=lambda x: (-int(x["stake_level"]), -float(x.get("ev") or 0.0), str(x.get("match") or "")))
    if not rows:
        return []
    header = [
        "📒 PORTAFOLIO BANKROLL DE PAPEL",
        "",
        f'Bankroll: COP {fmt_cop(pb["current_cop"])}',
        f'Exposición abierta: COP {fmt_cop(pb["open_exposure_cop"])} / COP {fmt_cop(pb["max_open_exposure_cop"])}',
        f'Apuestas abiertas: {len(rows)}',
        "",
    ]
    chunks: list[str] = []
    current = header[:]
    for i, row in enumerate(rows, start=1):
        line = (
            f'{i}. S{int(row["stake_level"])} | COP {fmt_cop(row["stake_cop"])} | '
            f'{row.get("house")} @{float(row.get("odds") or 0):.2f} | {row.get("match")}'
        )
        trial = "\n".join(current + [line, "", "DINERO REAL MATRIX: BLOQUEADO"])
        if len(trial) > 3800 and len(current) > len(header):
            current.append("DINERO REAL MATRIX: BLOQUEADO")
            chunks.append("\n".join(current))
            current = ["📒 PORTAFOLIO BANKROLL DE PAPEL — CONT.", "", line]
        else:
            current.append(line)
    current += ["", "DINERO REAL MATRIX: BLOQUEADO"]
    chunks.append("\n".join(current))
    return chunks


def green_message(c: dict[str, Any]) -> str:
    executed = c.get("execution") is not None
    paper = c.get("paper_bet") if isinstance(c.get("paper_bet"), dict) else None
    lines = [
        "🟢 SEÑAL VERDE SIMULADA",
        "",
        f'Partido: {c.get("match")}',
        f'Mercado: {c.get("market")}',
        f'P_MATRIX: {float(c["p_matrix"])*100:.2f}%',
        f'Casa: {c.get("house")}',
        f'Cuota física: {float(c["odds"]):.2f}',
        f'EV: {float(c["ev"])*100:+.2f}%',
    ]
    if paper is not None:
        lines += [
            f'Confianza/Staking: STAKE {int(paper["stake_level"])}',
            f'Apuesta de papel: COP {fmt_cop(paper["stake_cop"])}',
            f'Capital total de papel: COP {fmt_cop(paper["bankroll_before_cop"])}',
            f'Bankroll disponible antes: COP {fmt_cop(paper.get("available_before_cop") or 0)}',
            f'Bankroll disponible después: COP {fmt_cop(paper.get("available_after_cop") or 0)}',
        ]
    else:
        plan = c.get("paper_plan") if isinstance(c.get("paper_plan"), dict) else None
        if plan is not None:
            lines += [
                f'Stake MATRIX recomendado: STAKE {int(plan["stake_level"])}',
                f'Monto recomendado de papel: COP {fmt_cop(plan["stake_cop"])}',
                f'Bankroll disponible: COP {fmt_cop(plan.get("available_now_cop") or 0)}',
                "Apuesta de papel: NO ASIGNADA — límite de exposición alcanzado",
            ]
        else:
            lines += ["Apuesta de papel: NO ASIGNADA"]
    lines += [
        f'Hora Bogotá: {fmt_bogota(c.get("kickoff"))}',
        "Estado: PENDIENTE DE RESULTADO FINAL",
        f'Apuesta ejecutada por el usuario: {"SÍ" if executed else "NO"}',
        "DINERO REAL MATRIX: BLOQUEADO",
    ]
    return "\n".join(lines)


def paper_assignment_update_message(record: dict[str, Any], paper: dict[str, Any], pb: dict[str, Any]) -> str:
    return "\n".join([
        "🧪 ACTUALIZACIÓN — BANKROLL DE PAPEL Y STAKE",
        "",
        f'Partido: {record.get("match")}',
        f'Mercado: {record.get("market")}',
        f'P_MATRIX: {float(record.get("p_matrix") or 0.0)*100:.2f}%',
        f'Casa: {record.get("house")}',
        f'Cuota física: {float(record.get("odds") or 0.0):.2f}',
        f'EV: {float(record.get("ev") or 0.0)*100:+.2f}%',
        f'Stake MATRIX de papel: STAKE {int(paper["stake_level"])}',
        f'Apuesta de papel: COP {fmt_cop(paper["stake_cop"])}',
        f'Capital total de papel: COP {fmt_cop(pb.get("current_cop") or PAPER_BANKROLL_INITIAL_COP)}',
        f'Exposición abierta de papel: COP {fmt_cop(pb.get("open_exposure_cop") or 0)} / COP {fmt_cop(pb.get("max_open_exposure_cop") or 0)}',
        f'BANKROLL DISPONIBLE: COP {fmt_cop(pb.get("available_after_open_exposure_cop") or 0)}',
        "Solo simulación de papel. Sin ejecución automática.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def no_bet_message(c: dict[str, Any], offer: dict[str, Any]) -> str:
    return "\n".join([
        "🟡 NO APOSTAR — CORRECCIÓN DE CUOTA",
        "",
        f'Partido: {c.get("match")}',
        f'Mercado: {c.get("market")}',
        f'P_MATRIX congelada: {float(c["p_matrix"])*100:.2f}%',
        f'Casa observada: {offer.get("house")}',
        f'Cuota revalidada: {float(offer["odds"]):.2f}',
        f'EV actualizado: {float(offer["ev"])*100:+.2f}%',
        "Motivo: el EV dejó de ser positivo.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def no_bet_missing_quote_message(c: dict[str, Any], required_house_key: str | None) -> str:
    return "\n".join([
        "🟡 NO APOSTAR — REVALIDACIÓN PREMATCH",
        "",
        f'Partido: {c.get("match")}',
        f'Mercado: {c.get("market")}',
        f'P_MATRIX congelada: {float(c["p_matrix"])*100:.2f}%',
        f'Casa original: {c.get("house")}',
        "Motivo: ya no existe una cuota exacta Over 2.5 >1.50 verificable en la misma casa.",
        f'Casa requerida: {required_house_key or "NO_IDENTIFICADA"}',
        "La apuesta de papel queda cancelada antes del inicio.",
        "DINERO REAL MATRIX: BLOQUEADO",
    ])


def settlement_message(c: dict[str, Any], settlement: dict[str, Any], accum_u: float, accum_cop: float, paper_bankroll_after: float | None = None) -> str:
    title = "✅ GANADA" if settlement["won"] else "❌ PERDIDA"
    lines = [
        title,
        "",
        f'Partido: {c.get("match")}',
        f'Resultado final: {settlement["home_goals"]}-{settlement["away_goals"]}',
        f'Mercado: {c.get("market")}',
        f'Cuota congelada: {float(settlement["odds"]):.2f}',
        f'Rendimiento simulado: {float(settlement["shadow_profit_units"]):+.2f} unidades',
        f'Acumulado simulado: {accum_u:+.2f} unidades',
    ]
    if settlement.get("paper_stake_cop") is not None:
        lines += [
            f'Stake de papel: {int(settlement["paper_stake_level"])}',
            f'Apuesta de papel: COP {fmt_cop(settlement["paper_stake_cop"])}',
            f'Resultado papel: COP {fmt_cop(settlement["paper_profit_cop"])}',
        ]
        if paper_bankroll_after is not None:
            lines.append(f'Bankroll papel: COP {fmt_cop(paper_bankroll_after)}')
    if settlement.get("actual_stake_cop") is not None:
        stake_txt = f'{int(settlement["actual_stake_cop"]):,}'.replace(",", ".")
        profit_txt = f'{int(round(settlement["actual_profit_cop"])):,}'.replace(",", ".")
        accum_txt = f'{int(round(accum_cop)):,}'.replace(",", ".")
        lines += [
            f'Apuesta ejecutada por el usuario: COP {stake_txt}',
            f'Resultado económico: COP {profit_txt}',
            f'Acumulado apuestas registradas: COP {accum_txt}',
        ]
    lines.append("DINERO REAL MATRIX: BLOQUEADO PARA EJECUCIÓN AUTOMÁTICA")
    return "\n".join(lines)



def blocker_recovery_profile(gate_record: dict[str, Any]) -> dict[str, Any]:
    """Classify the exact blocking variable and the governed recovery path."""
    state = str(gate_record.get("state") or "")
    diag = gate_record.get("odds_api_net_diagnostic") or {}
    api_diag = gate_record.get("api_football_offer_diagnostic") or {}
    profile = {
        "state": state,
        "missing_or_failed_variable": "UNKNOWN",
        "recoverability": "REVIEW_REQUIRED",
        "sources_already_checked": [],
        "sources_available_for_recovery": [],
        "automatic_recovery_attempted": False,
        "automatic_recovery_exhausted": False,
        "final_disposition": "REVIEW_REQUIRED",
    }

    if state == "WAITING_FINAL_REVALIDATION_WINDOW":
        profile.update({
            "missing_or_failed_variable": "FINAL_PREMATCH_WINDOW_NOT_OPEN_YET",
            "recoverability": "TEMPORAL_WAIT",
            "sources_already_checked": ["MATRIX_PREMATCH_SCHEDULE"],
            "sources_available_for_recovery": ["API-Football", "odds-api.net", "Betano", "BetPlay", "Rushbet"],
            "final_disposition": "WAIT_FOR_120_MIN_WINDOW",
        })
        return profile

    if state == "BLOCKED_INVALID_KICKOFF":
        profile.update({
            "missing_or_failed_variable": "KICKOFF_DATETIME",
            "recoverability": "RECOVERABLE_IF_PREMATCH",
            "sources_already_checked": ["MATRIX_CANONICAL_CANDIDATE"],
            "sources_available_for_recovery": ["SofaScore", "Flashscore", "API-Football"],
            "final_disposition": "SOURCE_RECONCILIATION_REQUIRED",
        })
        return profile

    if state in {"BLOCKED_KICKOFF_REACHED", "BLOCKED_KICKOFF_REACHED_AFTER_REVALIDATION"}:
        profile.update({
            "missing_or_failed_variable": "PREMATCH_TIME_ELIGIBILITY",
            "recoverability": "NOT_RECOVERABLE_NO_BACKFILL",
            "sources_already_checked": ["MATRIX_PREMATCH_SCHEDULE"],
            "sources_available_for_recovery": [],
            "automatic_recovery_exhausted": True,
            "final_disposition": "DEFINITIVE_BLOCK_NO_BACKFILL",
        })
        return profile

    if state == "BLOCKED_KICKOFF_REACHED_LEGACY_UNOBSERVABLE":
        profile.update({
            "missing_or_failed_variable": "PRE_LIFECYCLE_MONITORING_HISTORY",
            "recoverability": "NOT_RECOVERABLE_NO_BACKFILL",
            "sources_already_checked": ["MATRIX_CANDIDATE_LIFECYCLE"],
            "sources_available_for_recovery": [],
            "automatic_recovery_exhausted": True,
            "final_disposition": "LEGACY_CASE_NOT_EVIDENCE_OF_CURRENT_MONITORING_BREACH",
        })
        return profile

    if state == "BLOCKED_KICKOFF_REACHED_MONITORING_BREACH":
        profile.update({
            "missing_or_failed_variable": "MONITORING_CADENCE_OR_DISCOVERY",
            "recoverability": "NOT_RECOVERABLE_NO_BACKFILL",
            "sources_already_checked": ["MATRIX_CANDIDATE_LIFECYCLE"],
            "sources_available_for_recovery": [],
            "automatic_recovery_exhausted": True,
            "final_disposition": "MONITORING_BREACH_REQUIRES_PREVENTIVE_FIX",
        })
        return profile

    if state in {"BLOCKED_NO_VALID_EXACT_AUTHORIZED_BOOK_OVER25", "BLOCKED_NONPOSITIVE_EV"}:
        provider_status = str(diag.get("status") or "")
        api_status = str(api_diag.get("status") or "")
        selected_offer = gate_record.get("offer") if isinstance(gate_record.get("offer"), dict) else None
        physical_offer = gate_record.get("physical_browser_offer") if isinstance(gate_record.get("physical_browser_offer"), dict) else None
        variable = "EXACT_AUTHORIZED_BOOK_OVER25_QUOTE" if state.startswith("BLOCKED_NO_VALID") else "POSITIVE_EXPECTED_VALUE"
        sources = ["API-Football", "odds-api.net"]
        recovery = ["Betano", "BetPlay", "Rushbet"]

        # A physically verified authorized-book quote with non-positive EV
        # is an economic block, not a provider-coverage or identity gap.
        if state == "BLOCKED_NONPOSITIVE_EV" and selected_offer is not None:
            if physical_offer is not None:
                sources.append(str(physical_offer.get("house") or "PHYSICAL_BOOK"))
            profile.update({
                "missing_or_failed_variable": "POSITIVE_EXPECTED_VALUE",
                "recoverability": "RECOVERABLE_WITH_BETTER_AUTHORIZED_QUOTE_WHILE_PREMATCH",
                "sources_already_checked": sources,
                "sources_available_for_recovery": ["Betano", "BetPlay", "Rushbet"],
                "automatic_recovery_attempted": True,
                "automatic_recovery_exhausted": False,
                "provider_diagnostic_status": provider_status or None,
                "api_football_offer_diagnostic_status": api_status or None,
                "api_football_offer_diagnostic": api_diag,
                "provider_discard_reasons": diag.get("discard_reasons") or {},
                "final_disposition": "RETRY_BETTER_AUTHORIZED_QUOTE_UNTIL_KICKOFF",
            })
            return profile

        if provider_status == "BLOCKED_EVENT_NOT_COVERED":
            if api_status == "BLOCKED_NO_AUTHORIZED_BOOK_COVERAGE":
                variable = "AUTHORIZED_BOOK_PROVIDER_COVERAGE"
            elif api_status == "BLOCKED_AUTHORIZED_BOOK_NO_TOTALS_MARKET":
                variable = "AUTHORIZED_BOOK_TOTALS_MARKET_COVERAGE"
            elif api_status == "BLOCKED_AUTHORIZED_BOOK_NO_OVER25_LINE":
                variable = "AUTHORIZED_BOOK_OVER25_LINE_COVERAGE"
            elif api_status == "BLOCKED_AUTHORIZED_BOOK_OVER25_ODDS_NOT_GT_1_50":
                variable = "AUTHORIZED_BOOK_MIN_ODDS_THRESHOLD"
            else:
                variable = "ODDS_PROVIDER_EVENT_COVERAGE"
            recovery = ["API-Football", "odds-api.net", "Betano", "BetPlay", "Rushbet"]
        elif provider_status in {"BLOCKED_IDENTITY_LOW_SCORE", "BLOCKED_IDENTITY_AMBIGUOUS", "BLOCKED_EVENT_ID_MISSING"}:
            variable = "EVENT_IDENTITY"
            recovery = ["SofaScore", "Flashscore", "API-Football", "odds-api.net"]
        elif provider_status in {"BLOCKED_FIXTURE_LOOKUP", "BLOCKED_CREDENTIAL_OR_KICKOFF"}:
            variable = "FIXTURE_OR_KICKOFF_BINDING"
            recovery = ["SofaScore", "Flashscore", "API-Football"]
        elif provider_status == "BLOCKED_SNAPSHOT_PROVIDER_ERROR":
            variable = "ODDS_PROVIDER_SNAPSHOT"
            recovery = ["odds-api.net", "API-Football", "Betano", "BetPlay", "Rushbet"]
        profile.update({
            "missing_or_failed_variable": variable,
            "recoverability": "RECOVERABLE_WHILE_PREMATCH",
            "sources_already_checked": sources,
            "sources_available_for_recovery": recovery,
            "automatic_recovery_attempted": True,
            "automatic_recovery_exhausted": False,
            "provider_diagnostic_status": provider_status or None,
            "provider_discard_reasons": diag.get("discard_reasons") or {},
            "final_disposition": "KEEP_RETRYING_UNTIL_KICKOFF_OR_RECOVERED",
        })
        return profile

    if state == "BLOCKED_NO_FRESH_PINNACLE_REFERENCE":
        fallback = diag.get("api_football_pinnacle_fallback") or {}
        fallback_status = str(fallback.get("status") or "")
        sources = ["odds-api.net"]
        if fallback_status:
            sources.append("API-Football Pinnacle bookmaker_id=4")
        profile.update({
            "missing_or_failed_variable": "PINNACLE_FRESH_REFERENCE",
            "recoverability": "RECOVERABLE_WHILE_PREMATCH",
            "sources_already_checked": sources,
            "sources_available_for_recovery": ["odds-api.net", "API-Football Pinnacle bookmaker_id=4"],
            "automatic_recovery_attempted": bool(fallback_status),
            "automatic_recovery_exhausted": False,
            "api_football_pinnacle_fallback_status": fallback_status or None,
            "api_football_pinnacle_quote_age_seconds": fallback.get("provider_quote_age_seconds"),
            "api_football_pinnacle_provider_quote_updated_at_utc": fallback.get("provider_quote_updated_at_utc"),
            "final_disposition": "RETRY_FRESH_PINNACLE_UNTIL_KICKOFF",
        })
        return profile

    if state == "BLOCKED_QUALITY_P_MATRIX_BELOW_60PCT":
        profile.update({
            "missing_or_failed_variable": "P_MATRIX_QUALITY_THRESHOLD",
            "recoverability": "NOT_RECOVERABLE_BY_ODDS_OR_EXTERNAL_DATA",
            "sources_already_checked": ["MATRIX_FROZEN_P_MATRIX"],
            "sources_available_for_recovery": [],
            "automatic_recovery_exhausted": True,
            "final_disposition": "DEFINITIVE_BLOCK_MODEL_QUALITY",
        })
        return profile

    if state == "BLOCKED_QUALITY_REVALIDATED_EV_BELOW_5PCT":
        profile.update({
            "missing_or_failed_variable": "REVALIDATED_EXPECTED_VALUE_THRESHOLD",
            "recoverability": "RECOVERABLE_WITH_BETTER_AUTHORIZED_QUOTE_WHILE_PREMATCH",
            "sources_already_checked": ["API-Football", "odds-api.net"],
            "sources_available_for_recovery": ["Betano", "BetPlay", "Rushbet"],
            "automatic_recovery_attempted": True,
            "final_disposition": "RETRY_AUTHORIZED_BOOKS_UNTIL_KICKOFF",
        })
        return profile

    if state in {"BLOCKED_CORRELATED_EXPOSURE", "BLOCKED_CORRELATED_RISK_IDENTITY_INCOMPLETE", "BLOCKED_LEAGUE_CONCENTRATION_CAP"}:
        profile.update({
            "missing_or_failed_variable": "CORRELATED_RISK_OR_CONCENTRATION_CAP",
            "recoverability": "POLICY_BLOCK_NOT_DATA_GAP",
            "sources_already_checked": ["MATRIX_CORRELATED_RISK_LEDGER"],
            "sources_available_for_recovery": [],
            "automatic_recovery_exhausted": True,
            "final_disposition": "DEFINITIVE_BLOCK_RISK_POLICY",
        })
        return profile

    profile["sources_already_checked"] = ["MATRIX_PRE_SEND_GATE"]
    profile["final_disposition"] = "MANUAL_CLASSIFICATION_REQUIRED"
    return profile


def build_blocker_recovery_audit(
    ledger: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    existing_sent_keys: set[str],
    now: datetime,
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    counts_by_state: dict[str, int] = {}
    counts_by_variable: dict[str, int] = {}
    counts_by_recoverability: dict[str, int] = {}
    for key, candidate in sorted(candidates.items(), key=lambda kv: (str(kv[1].get("kickoff")), kv[0])):
        if key in existing_sent_keys or candidate.get("sport") != "football":
            continue
        gate = ledger.get("pre_send_gate", {}).get(key)
        if not isinstance(gate, dict):
            continue
        profile = blocker_recovery_profile(gate)
        state = str(gate.get("state") or "UNKNOWN")
        kickoff_dt = parse_dt(candidate.get("kickoff"))
        time_state = "PREMATCH"
        if kickoff_dt is not None and kickoff_dt <= now:
            time_state = "PAST_KICKOFF"
            if str(profile.get("recoverability") or "") in {
                "RECOVERABLE_WHILE_PREMATCH",
                "RECOVERABLE_WITH_BETTER_AUTHORIZED_QUOTE_WHILE_PREMATCH",
                "TEMPORAL_WAIT",
                "REVIEW_REQUIRED",
            }:
                profile["recoverability"] = "NOT_RECOVERABLE_NO_BACKFILL"
                profile["automatic_recovery_exhausted"] = True
                profile["final_disposition"] = "PAST_KICKOFF_NO_BACKFILL"
                profile["sources_available_for_recovery"] = []
        variable = str(profile.get("missing_or_failed_variable") or "UNKNOWN")
        recoverability = str(profile.get("recoverability") or "REVIEW_REQUIRED")
        counts_by_state[state] = counts_by_state.get(state, 0) + 1
        counts_by_variable[variable] = counts_by_variable.get(variable, 0) + 1
        counts_by_recoverability[recoverability] = counts_by_recoverability.get(recoverability, 0) + 1
        provider_diag = gate.get("odds_api_net_diagnostic") or {}
        api_offer_diag = gate.get("api_football_offer_diagnostic") or {}
        current_offer = gate.get("offer") if isinstance(gate.get("offer"), dict) else {}
        records.append({
            "signal_key": key,
            "fixture_id": candidate.get("fixture_id"),
            "match": candidate.get("match"),
            "league_id": candidate.get("league_id"),
            "kickoff": candidate.get("kickoff"),
            "p_matrix": candidate.get("p_matrix"),
            "current_house": current_offer.get("house") or candidate.get("house"),
            "current_odds": current_offer.get("odds") if current_offer else candidate.get("odds"),
            "current_ev": current_offer.get("ev") if current_offer else candidate.get("ev"),
            "selected_quote_provider": current_offer.get("provider") if current_offer else None,
            "physical_evidence_path": current_offer.get("physical_evidence_path") if current_offer else None,
            "gate_state": state,
            **profile,
            "provider_identity_top_scores": provider_diag.get("identity_top_scores") or [],
            "provider_identity_top_candidates": (provider_diag.get("identity_top_candidates") or [])[:5],
            "api_football_offer_diagnostic_status": api_offer_diag.get("status"),
            "api_football_authorized_books_seen": api_offer_diag.get("authorized_books_seen") or [],
            "api_football_goals_over_under_books": api_offer_diag.get("goals_over_under_books") or [],
            "api_football_over25_books": api_offer_diag.get("over25_books") or [],
            "api_football_eligible_offer_count": api_offer_diag.get("eligible_offer_count"),
            "checked_at_utc": gate.get("checked_at_utc") or now.isoformat(),
            "time_state_at_audit": time_state,
            "real_money": "BLOCKED",
        })
    return {
        "schema": "MATRIX_TELEGRAM_BLOCKER_RECOVERY_AUDIT_V1",
        "generated_at_utc": now.isoformat(),
        "policy": {
            "blocked_does_not_mean_discarded": True,
            "missing_is_not_zero": True,
            "no_silent_imputation": True,
            "no_backfill_after_kickoff": True,
            "source_order": ["SofaScore", "Flashscore", "API-Football", "odds-api.net", "Betano", "BetPlay", "Betsson", "Bwin", "Codere", "Luckia", "MrYoker", "Rivalo", "Rushbet", "Sportium", "Stake", "Wplay", "YaJuego", "Zamba"],
            "automatic_quote_recovery": ["API-Football", "odds-api.net"],
            "browser_or_bookmaker_recovery_when_needed": ["SofaScore", "Flashscore", "Betano", "BetPlay", "Betsson", "Bwin", "Codere", "Luckia", "MrYoker", "Rivalo", "Rushbet", "Sportium", "Stake", "Wplay", "YaJuego", "Zamba"],
            "real_money": "BLOCKED",
        },
        "summary": {
            "records": len(records),
            "counts_by_state": dict(sorted(counts_by_state.items())),
            "counts_by_variable": dict(sorted(counts_by_variable.items())),
            "counts_by_recoverability": dict(sorted(counts_by_recoverability.items())),
        },
        "records": records,
    }

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    odds_api_net_key = os.environ.get("ODDS_API_NET_KEY", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN_NOT_CONFIGURED")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID_NOT_CONFIGURED")
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")

    now = now_utc()
    today = now.astimezone(BOGOTA).date()
    dates = [str(today + timedelta(days=1)), str(today), str(today - timedelta(days=1))]
    football = discover_football(dates)
    tennis = discover_tennis(dates)
    candidates = {**football, **tennis}

    ledger = load_json(LEDGER, {
        "schema": "MATRIX_TELEGRAM_SIGNAL_LEDGER_V2",
        "created_at_utc": now.isoformat(),
        "sent": [],
        "quote_state": {},
        "corrections": [],
        "settlements": [],
        "run_history": [],
        "paper_bankroll": {},
    })
    ledger["schema"] = "MATRIX_TELEGRAM_SIGNAL_LEDGER_V2"
    ledger.setdefault("sent", [])
    ledger.setdefault("quote_state", {})
    ledger.setdefault("corrections", [])
    ledger.setdefault("settlements", [])
    ledger.setdefault("run_history", [])
    ledger.setdefault("paper_bankroll", {})
    ledger.setdefault("pre_send_gate", {})
    ledger.setdefault("candidate_lifecycle", {})

    # Recover physically delivered Telegram signals when a prior Git persistence
    # race lost the sent[] append. Recovery is evidence-driven and never assigns
    # paper or real-money exposure retroactively.
    recovered_sent = load_json(SENT_RECOVERY_OVERRIDES, {"records": []})
    existing_sent_recovery_keys = {
        str(x.get("signal_key") or "")
        for x in ledger.get("sent", [])
        if isinstance(x, dict)
    }
    for recovered in recovered_sent.get("records", []):
        if not isinstance(recovered, dict):
            continue
        recovered_key = str(recovered.get("signal_key") or "")
        if not recovered_key or recovered_key in existing_sent_recovery_keys:
            continue
        record = dict(recovered)
        record["paper_bet"] = None
        record["execution"] = None
        record["matrix_real_money"] = "BLOQUEADO"
        ledger["sent"].append(record)
        existing_sent_recovery_keys.add(recovered_key)

    pre_risk_bankroll = recalc_paper_bankroll(ledger)
    correlated_risk_calibration = calibrate_paper_correlated_exposure(
        ledger,
        initial_bankroll_cop=PAPER_BANKROLL_INITIAL_COP,
        unit_cop=PAPER_UNIT_COP,
        max_signals_per_tournament_day=PAPER_MAX_SIGNALS_PER_LEAGUE_DAY,
        daily_policy_cap_fraction=PAPER_DAILY_BASE_EXPOSURE_FRACTION,
    )
    ledger["correlated_risk_calibration"] = correlated_risk_calibration

    risk_calibration = calibrate_correlated_risk_from_ledger(ledger)
    risk_evidence = calibration_evidence(risk_calibration)
    risk_evidence["generated_at_utc"] = now.isoformat()
    risk_evidence["integration"] = {
        "stage": "FINAL_PREMATCH_BEFORE_TELEGRAM",
        "fail_closed": True,
        "stake_basis": "TEMPORARY_FLAT_1U_CAP_17OCT2026",
        "real_money": "BLOCKED",
    }
    CORRELATED_RISK_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    CORRELATED_RISK_EVIDENCE.write_text(
        json.dumps(risk_evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    risk_bankroll = float(recalc_paper_bankroll(ledger).get("current_cop") or PAPER_BANKROLL_INITIAL_COP)
    risk_limits = correlated_risk_limits_from_physical_calibration(
        correlated_risk_calibration,
        bankroll=risk_bankroll,
    )
    risk_existing_exposures = current_correlated_exposures(ledger)
    risk_pending_exposures: list[ExposureRecord] = []

    session = requests.Session()
    ev_lab = load_json(EV_MARGINAL_LAB_EVIDENCE, {
        "schema": "MATRIX_EV_MARGINAL_SHADOW_LAB_V1",
        "created_at_utc": now.isoformat(),
        "observations": [],
    })
    ev_lab["schema"] = "MATRIX_EV_MARGINAL_SHADOW_LAB_V1"
    ev_lab.setdefault("observations", [])
    ev_lab_existing_keys = {
        str(x.get("signal_key") or "")
        for x in ev_lab["observations"]
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    ev_lab_new_now = 0
    pre_send_quote_checks = 0
    pre_send_waiting = 0
    pre_send_blocked = 0
    pre_send_passed = 0
    existing_sent_keys = {
        str(x.get("signal_key") or "")
        for x in ledger.get("sent", [])
        if isinstance(x, dict) and str(x.get("signal_key") or "")
    }
    monitoring_breaches_now = 0
    for key, candidate in candidates.items():
        if key in existing_sent_keys:
            continue
        if candidate.get("sport") != "football" or candidate.get("eligible_green") is not True:
            continue

        lifecycle = ledger["candidate_lifecycle"].setdefault(key, {
            "fixture_id": candidate.get("fixture_id"),
            "match": candidate.get("match"),
            "kickoff": candidate.get("kickoff"),
            "first_seen_utc": now.isoformat(),
            "final_revalidation_attempts": 0,
            "monitoring_breach": False,
        })
        lifecycle["last_seen_utc"] = now.isoformat()
        gate_state = prematch_revalidation_state(candidate, now)
        gate_record = {
            "checked_at_utc": now.isoformat(),
            "fixture_id": candidate.get("fixture_id"),
            "kickoff": candidate.get("kickoff"),
            "league_id": candidate.get("league_id"),
            "window_minutes": GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES,
            "state": gate_state,
        }

        # Preserve the first definitive prematch reason instead of overwriting it
        # later with KICKOFF_REACHED on historical scans.
        if gate_state == "BLOCKED_KICKOFF_REACHED":
            prior_terminal = lifecycle.get("first_terminal_state")
            attempts = int(lifecycle.get("final_revalidation_attempts") or 0)
            if prior_terminal:
                gate_record["state"] = str(prior_terminal)
                gate_record["time_state_now"] = "KICKOFF_REACHED"
                gate_record["preserved_terminal_reason"] = True
            elif attempts <= 0:
                first_seen = parse_dt(lifecycle.get("first_seen_utc"))
                kickoff_dt = parse_dt(candidate.get("kickoff"))
                # Historical candidates first observed only after kickoff cannot
                # prove a monitoring failure because lifecycle tracking did not
                # exist before this fix. Keep them explicitly unobservable.
                if first_seen is not None and kickoff_dt is not None and first_seen >= kickoff_dt:
                    gate_record["state"] = "BLOCKED_KICKOFF_REACHED_LEGACY_UNOBSERVABLE"
                    lifecycle["monitoring_breach"] = False
                    lifecycle["legacy_unobservable"] = True
                else:
                    gate_record["state"] = "BLOCKED_KICKOFF_REACHED_MONITORING_BREACH"
                    if register_monitoring_breach(lifecycle, now):
                        monitoring_breaches_now += 1
            else:
                gate_record["state"] = "BLOCKED_KICKOFF_REACHED_AFTER_REVALIDATION"
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = gate_record["state"]
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue

        if gate_state == "WAITING_FINAL_REVALIDATION_WINDOW":
            lifecycle["last_waiting_check_utc"] = now.isoformat()
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = gate_state
            ledger["pre_send_gate"][key] = gate_record
            pre_send_waiting += 1
            continue
        if gate_state != "READY_FOR_FINAL_REVALIDATION":
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = gate_state
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue

        lifecycle.setdefault("first_ready_for_final_revalidation_utc", now.isoformat())
        lifecycle["last_ready_for_final_revalidation_utc"] = now.isoformat()
        required_house_key = bookmaker_key(candidate.get("house"))
        api_football_offer_diagnostic: dict[str, Any] = {}
        primary_offer = exact_over25_offer(
            session,
            api_key,
            str(candidate["fixture_id"]),
            float(candidate["p_matrix"]),
            required_house_key,
            api_football_offer_diagnostic,
        )
        odds_api_net_diagnostic: dict[str, Any] = {}
        fallback_offer = odds_api_net_exact_over25_offer(
            session,
            odds_api_net_key,
            str(candidate["fixture_id"]),
            candidate.get("kickoff"),
            float(candidate["p_matrix"]),
            api_key,
            odds_api_net_diagnostic,
        )
        physical_offer = physical_book_over25_offer(
            str(candidate["fixture_id"]),
            float(candidate["p_matrix"]),
            now,
            required_house_key=None,
        )
        comparable = [x for x in (primary_offer, fallback_offer, physical_offer) if isinstance(x, dict)]
        offer = max(comparable, key=lambda x: float(x.get("ev") or -999.0)) if comparable else None
        pre_send_quote_checks += 1
        lifecycle["final_revalidation_attempts"] = int(lifecycle.get("final_revalidation_attempts") or 0) + 1
        lifecycle["last_final_revalidation_at_utc"] = now.isoformat()
        gate_record["required_house_key"] = required_house_key
        gate_record["primary_same_house_offer"] = primary_offer
        gate_record["api_football_offer_diagnostic"] = api_football_offer_diagnostic
        gate_record["odds_api_net_multi_book_offer"] = fallback_offer
        gate_record["physical_browser_offer"] = physical_offer
        gate_record["odds_api_net_diagnostic"] = odds_api_net_diagnostic
        gate_record["offer"] = offer
        gate_record["selected_quote_provider"] = (offer or {}).get("provider") or ("api-football" if offer else None)
        gate_record["multi_book_fallback_used"] = bool(offer is not None and offer is fallback_offer)
        final_quote_state = final_prematch_quote_state(offer)
        if final_quote_state != "PASS_FINAL_PREMATCH_REVALIDATION":
            gate_record["state"] = final_quote_state
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = final_quote_state
            lifecycle.setdefault("first_terminal_state", final_quote_state)
            lifecycle.setdefault("first_terminal_at_utc", now.isoformat())
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue
        odds_api_net_diagnostic = augment_sharp_diagnostic_with_api_football_fallback(
            odds_api_net_diagnostic,
            session=session,
            api_key=api_key,
            fixture_id=str(candidate["fixture_id"]),
            p=float(candidate["p_matrix"]),
        )
        sharp_state, sharp_detail = sharp_reference_gate_state(odds_api_net_diagnostic)
        gate_record["sharp_reference_gate"] = sharp_detail
        gate_record["sharp_reference_state"] = sharp_state
        if sharp_state != "PASS_SHARP_REFERENCE_GATE":
            gate_record["state"] = sharp_state
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = sharp_state
            lifecycle.setdefault("first_terminal_state", sharp_state)
            lifecycle.setdefault("first_terminal_at_utc", now.isoformat())
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue
        offer_ev = float(offer["ev"])
        offer_odds = float(offer["odds"])
        p_matrix = float(candidate["p_matrix"])
        if (
            key not in ev_lab_existing_keys
            and is_ev_marginal_lab_candidate(p_matrix, offer_odds, offer_ev)
        ):
            lab_risk_state, lab_risk_detail, _ = correlated_risk_gate_state(
                candidate,
                bankroll=risk_bankroll,
                limits=risk_limits,
                existing=risk_existing_exposures + risk_pending_exposures,
            )
            band = ev_marginal_band(offer_ev)
            ev_lab["observations"].append({
                "signal_key": key,
                "fixture_id": candidate.get("fixture_id"),
                "match": candidate.get("match"),
                "league_id": candidate.get("league_id"),
                "kickoff": candidate.get("kickoff"),
                "frozen_at_utc": now.isoformat(),
                "p_matrix": p_matrix,
                "house": offer.get("house"),
                "decimal_odds": offer_odds,
                "ev": offer_ev,
                "ev_band": band,
                "selected_quote_provider": (offer or {}).get("provider") or "api-football",
                "sharp_reference_state": sharp_state,
                "sharp_reference_gate": sharp_detail,
                "correlated_risk_state_shadow": lab_risk_state,
                "correlated_risk_shadow": lab_risk_detail,
                "production_signal_emitted": False,
                "production_ev_gate": SIGNAL_QUALITY_MIN_REVALIDATED_EV,
                "lab_only": True,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            })
            ev_lab_existing_keys.add(key)
            ev_lab_new_now += 1

        quality_state = signal_quality_gate_state(candidate, offer)
        gate_record["quality_policy"] = SIGNAL_QUALITY_POLICY
        gate_record["quality_min_p_matrix"] = SIGNAL_QUALITY_MIN_P_MATRIX
        gate_record["quality_min_revalidated_ev"] = SIGNAL_QUALITY_MIN_REVALIDATED_EV
        gate_record["quality_state"] = quality_state
        if quality_state != "PASS_API_COST_RECOVERY_PRECISION_GATE":
            gate_record["state"] = quality_state
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = quality_state
            lifecycle.setdefault("first_terminal_state", quality_state)
            lifecycle.setdefault("first_terminal_at_utc", now.isoformat())
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue
        risk_state, risk_detail, risk_proposed = correlated_risk_gate_state(
            candidate,
            bankroll=risk_bankroll,
            limits=risk_limits,
            existing=risk_existing_exposures + risk_pending_exposures,
        )
        gate_record["correlated_risk"] = risk_detail
        gate_record["correlated_risk_state"] = risk_state
        if risk_state != "PASS_CORRELATED_EXPOSURE_GATE":
            gate_record["state"] = risk_state
            candidate["eligible_green"] = False
            candidate["send_gate_status"] = risk_state
            lifecycle.setdefault("first_terminal_state", risk_state)
            lifecycle.setdefault("first_terminal_at_utc", now.isoformat())
            ledger["pre_send_gate"][key] = gate_record
            pre_send_blocked += 1
            continue
        if risk_proposed is not None:
            risk_pending_exposures.append(risk_proposed)

        candidate["house"] = offer["house"]
        candidate["odds"] = offer["odds"]
        candidate["ev"] = offer["ev"]
        candidate["physical_quote_verified"] = True
        candidate["send_gate_status"] = quality_state
        candidate["pre_send_revalidated_at_utc"] = now.isoformat()
        gate_record["state"] = candidate["send_gate_status"]
        ledger["pre_send_gate"][key] = gate_record
        pre_send_passed += 1

    paper_enabled = os.environ.get("PAPER_BANKROLL", "DISABLED").strip().upper() == "ENABLED"
    paper_reconciliation = reconcile_existing_paper_state(ledger, now)
    pb = recalc_paper_bankroll(ledger)
    assigned_paper_now = 0
    if paper_enabled:
        day_candidates: dict[str, list[dict[str, Any]]] = {}
        priority = []
        for key, candidate in candidates.items():
            if candidate.get("eligible_green") is not True:
                continue
            if not candidate.get("physical_quote_verified") or float(candidate["odds"]) <= 1.50 or float(candidate["ev"]) <= 0:
                continue
            kickoff = parse_dt(candidate.get("kickoff"))
            if kickoff is None or kickoff <= now:
                continue
            day = str(kickoff.astimezone(BOGOTA).date())
            day_candidates.setdefault(day, []).append(candidate)
            record = next((x for x in ledger["sent"] if str(x.get("signal_key")) == key), None)
            if isinstance(record, dict) and isinstance(record.get("paper_bet"), dict):
                continue
            level = paper_stake_level(candidate)
            priority.append((day, level, float(candidate["ev"]), key, candidate, record))
        daily_exposure = paper_daily_exposure_by_date(ledger)
        league_day_counts: dict[tuple[str, str], int] = {}
        for existing in ledger.get("sent", []):
            bet = existing.get("paper_bet")
            if not isinstance(bet, dict):
                continue
            if str(bet.get("status") or "").upper() in {"CANCELLED_NO_BET", "VOID_POSTPONED"}:
                continue
            day = bet.get("kickoff_bogota_date") or paper_kickoff_date(existing.get("kickoff"))
            league_id = str(existing.get("league_id") or "").strip()
            if day and league_id:
                k = (str(day), league_id)
                league_day_counts[k] = league_day_counts.get(k, 0) + 1
        daily_caps = {day: paper_daily_cap_fraction(rows) for day, rows in day_candidates.items()}
        pb["daily_cap_by_date"] = {
            day: {
                "cap_fraction": daily_caps[day],
                "cap_cop": float(pb["current_cop"]) * daily_caps[day],
                "eligible_signals": len(rows),
                "stake3_signals": sum(1 for x in rows if paper_stake_level(x) == 3),
                "tier2_or_3_signals": sum(1 for x in rows if paper_stake_level(x) >= 2),
            }
            for day, rows in day_candidates.items()
        }
        priority.sort(key=lambda x: (x[0], -x[1], -x[2], str(x[4].get("kickoff")), x[3]))
        running_open_exposure = float(pb.get("open_exposure_cop") or 0.0)
        correlated_risk_provisional: list[dict[str, Any]] = []
        for day, level, _, key, candidate, record in priority:
            correlated_risk_decision = assess_paper_correlated_exposure(
                ledger,
                {
                    "fixture_id": candidate.get("fixture_id"),
                    "tournament_key": candidate.get("league_id"),
                    "operational_date": day,
                    "stake_cop": paper_stake_cop(level),
                },
                calibration=correlated_risk_calibration,
                bankroll_cop=float(pb["current_cop"]),
                provisional=correlated_risk_provisional,
            )
            candidate["correlated_risk"] = correlated_risk_decision
            ledger["pre_send_gate"][key] = {
                **(ledger["pre_send_gate"].get(key) or {}),
                "correlated_risk": correlated_risk_decision,
            }
            if correlated_risk_decision.get("allowed") is not True:
                candidate["eligible_green"] = False
                candidate["send_gate_status"] = correlated_risk_decision.get("status")
                candidate["paper_plan"] = {
                    "stake_level": level,
                    "stake_cop": paper_stake_cop(level),
                    "assignment_status": "NO_ASIGNADO_RIESGO_CORRELACIONADO",
                    "reason": ",".join(correlated_risk_decision.get("blocked_reasons") or []),
                    "real_money": "BLOCKED",
                }
                ledger["pre_send_gate"][key]["state"] = candidate["send_gate_status"]
                pre_send_blocked += 1
                continue
            league_key = paper_league_day_key(candidate)
            if league_key is not None and paper_league_concentration_blocked(league_day_counts.get(league_key, 0)):
                candidate["eligible_green"] = False
                candidate["send_gate_status"] = "BLOCKED_LEAGUE_CONCENTRATION_CAP"
                candidate["paper_plan"] = {
                    "stake_level": level,
                    "stake_cop": paper_stake_cop(level),
                    "assignment_status": "NO_ASIGNADO_RIESGO_CORRELACIONADO",
                    "reason": "LEAGUE_CONCENTRATION_CAP_REACHED",
                    "league_id": league_key[1],
                    "league_day_cap": PAPER_MAX_SIGNALS_PER_LEAGUE_DAY,
                    "real_money": "BLOCKED",
                }
                ledger["pre_send_gate"][key] = {
                    **(ledger["pre_send_gate"].get(key) or {}),
                    "state": "BLOCKED_LEAGUE_CONCENTRATION_CAP",
                    "league_id": league_key[1],
                    "league_day_cap": PAPER_MAX_SIGNALS_PER_LEAGUE_DAY,
                }
                pre_send_blocked += 1
                continue
            stake = paper_stake_cop(level)
            max_day = float(pb["current_cop"]) * daily_caps.get(day, PAPER_DAILY_BASE_EXPOSURE_FRACTION)
            used_day = float(daily_exposure.get(day, 0.0))
            if used_day + stake > max_day + 1e-9:
                available_now = max(0.0, float(pb["current_cop"]) - running_open_exposure)
                candidate["paper_plan"] = {
                    "stake_level": level,
                    "stake_cop": stake,
                    "available_now_cop": available_now,
                    "daily_cap_cop": max_day,
                    "daily_used_cop": used_day,
                    "assignment_status": "NO_ASIGNADO_LIMITE_EXPOSICION",
                    "reason": "DAILY_EXPOSURE_CAP_REACHED",
                    "real_money": "BLOCKED",
                }
                if isinstance(record, dict):
                    record["paper_plan"] = candidate["paper_plan"]
                continue
            available_before = max(0.0, float(pb["current_cop"]) - running_open_exposure)
            available_after = max(0.0, available_before - stake)
            paper = {
                "status": "OPEN",
                "stake_level": level,
                "stake_units": float(PAPER_STAKE_LEVELS[level]),
                "stake_cop": stake,
                "bankroll_before_cop": float(pb["current_cop"]),
                "available_before_cop": available_before,
                "available_after_cop": available_after,
                "open_exposure_before_cop": running_open_exposure,
                "open_exposure_after_cop": running_open_exposure + stake,
                "kickoff_bogota_date": day,
                "daily_cap_fraction": daily_caps.get(day, PAPER_DAILY_BASE_EXPOSURE_FRACTION),
                "assigned_at_utc": now.isoformat(),
                "policy": "FIXED_UNIT_0_5PCT_INITIAL_BANKROLL_CONFIDENCE_1_2_3_DYNAMIC_DAILY_30_40",
                "real_money": "BLOCKED",
            }
            candidate["paper_bet"] = paper
            if isinstance(record, dict):
                paper["assignment_source"] = "RETROACTIVE_EXISTING_SIGNAL"
                paper["telegram_update_required"] = True
                record["paper_bet"] = paper
            else:
                paper["assignment_source"] = "NEW_SIGNAL_GREEN_MESSAGE"
                paper["telegram_update_required"] = False
            daily_exposure[day] = used_day + stake
            running_open_exposure += stake
            if league_key is not None:
                league_day_counts[league_key] = league_day_counts.get(league_key, 0) + 1
            correlated_risk_provisional.append({
                "fixture_id": candidate.get("fixture_id"),
                "tournament_key": candidate.get("league_id"),
                "operational_date": day,
                "stake_cop": stake,
            })
            assigned_paper_now += 1
        pb["daily_exposure_by_date"] = daily_exposure
        pb = recalc_paper_bankroll(ledger)

    paper_assignment_updates_now = 0
    if paper_enabled:
        for record in ledger["sent"]:
            paper = record.get("paper_bet")
            if not isinstance(paper, dict) or paper.get("telegram_update_required") is not True:
                continue
            try:
                mid = send_telegram(session, token, chat_id, paper_assignment_update_message(record, paper, pb))
            except Exception as exc:
                ledger.setdefault("delivery_failures", []).append({
                    "signal_key": record.get("signal_key"),
                    "fixture_id": record.get("fixture_id"),
                    "match": record.get("match"),
                    "market": record.get("market"),
                    "attempted_at_utc": now.isoformat(),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "status": "PAPER_STAKE_UPDATE_DELIVERY_FAILED_RETRY_NEXT_RUN",
                })
                continue
            paper["telegram_update_required"] = False
            paper["assignment_message_id"] = mid
            paper["assignment_message_sent_at_utc"] = now.isoformat()
            paper_assignment_updates_now += 1

    sent_by_key = {str(x.get("signal_key")): x for x in ledger["sent"]}
    settled_keys = {str(x.get("signal_key")) for x in ledger["settlements"]}
    sent_now = corrections_now = settlements_now = quote_checks = 0
    rectifications_now = economic_updates_now = 0
    delivery_failures_now = 0
    ledger.setdefault("delivery_failures", [])

    for key, c in sorted(candidates.items(), key=lambda kv: (str(kv[1].get("kickoff")), kv[0])):
        if key in sent_by_key:
            record = sent_by_key[key]
            for field in ("sport", "fixture_id", "match", "league_id", "market", "p_matrix", "house", "odds", "ev", "kickoff", "source", "execution", "paper_bet", "paper_plan", "send_gate_status", "pre_send_revalidated_at_utc"):
                if record.get(field) is None:
                    record[field] = c.get(field)
        if c.get("eligible_green") is not True:
            continue
        if not c.get("physical_quote_verified") or float(c["odds"]) <= 1.50 or float(c["ev"]) <= 0:
            continue
        if key not in sent_by_key:
            try:
                mid = send_telegram(session, token, chat_id, green_message(c))
            except Exception as exc:
                ledger["delivery_failures"].append({
                    "signal_key": key,
                    "fixture_id": c["fixture_id"],
                    "match": c["match"],
                    "market": c["market"],
                    "house": c["house"],
                    "odds": c["odds"],
                    "ev": c["ev"],
                    "attempted_at_utc": now.isoformat(),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                    "status": "DELIVERY_FAILED_RETRY_NEXT_RUN",
                })
                delivery_failures_now += 1
                continue
            record = {
                "signal_key": key,
                "sport": c["sport"],
                "fixture_id": c["fixture_id"],
                "match": c["match"],
                "league_id": c.get("league_id"),
                "market": c["market"],
                "p_matrix": c["p_matrix"],
                "house": c["house"],
                "odds": c["odds"],
                "ev": c["ev"],
                "kickoff": c["kickoff"],
                "source": c["source"],
                "execution": c.get("execution"),
                "paper_bet": c.get("paper_bet"),
                "paper_plan": c.get("paper_plan"),
                "send_gate_status": c.get("send_gate_status"),
                "pre_send_revalidated_at_utc": c.get("pre_send_revalidated_at_utc"),
                "sent_at_utc": now.isoformat(),
                "telegram_message_id": mid,
                "status": "ENVIADO_OK",
                "matrix_real_money": "BLOQUEADO",
            }
            ledger["sent"].append(record)
            sent_by_key[key] = record
            # Durability boundary: once Telegram confirms delivery, persist it
            # locally before any later notification, settlement, or audit step.
            persist_ledger_checkpoint(ledger)
            sent_now += 1

    if paper_enabled:
        pb = recalc_paper_bankroll(ledger)
        if pb.get("balance_definition_message_id") is None:
            pb["balance_definition_message_id"] = send_telegram(
                session, token, chat_id, paper_bankroll_balance_correction_message(pb)
            )
            pb["balance_definition_sent_at_utc"] = now.isoformat()
        if pb.get("activation_message_id") is None:
            mid = send_telegram(session, token, chat_id, paper_bankroll_activation_message(pb, assigned_paper_now))
            pb["activation_message_id"] = mid
            pb["activated_at_utc"] = now.isoformat()
        if pb.get("exposure_policy_30_40_message_id") is None:
            pb["exposure_policy_30_40_message_id"] = send_telegram(session, token, chat_id, paper_exposure_policy_message(pb))
            pb["exposure_policy_30_40_sent_at_utc"] = now.isoformat()
        if pb.get("portfolio_seed_message_ids") is None:
            portfolio_ids = [send_telegram(session, token, chat_id, text) for text in paper_portfolio_messages(ledger)]
            pb["portfolio_seed_message_ids"] = portfolio_ids
            pb["portfolio_seed_sent_at_utc"] = now.isoformat()
        if pb.get("initial_cohort_fully_assigned") is True and pb.get("full_initial_cohort_message_ids") is None:
            cohort_ids = [send_telegram(session, token, chat_id, paper_full_cohort_message(pb))]
            cohort_ids.extend(send_telegram(session, token, chat_id, text) for text in paper_portfolio_messages(ledger))
            pb["full_initial_cohort_message_ids"] = cohort_ids
            pb["full_initial_cohort_sent_at_utc"] = now.isoformat()

    # Rectify legacy quote corrections that compared a different house than the original signal.
    for correction in ledger["corrections"]:
        if correction.get("status") != "NO_APOSTAR_ENVIADO" or correction.get("rectification_message_id") is not None:
            continue
        key = str(correction.get("signal_key") or "")
        record = sent_by_key.get(key)
        c = candidates.get(key)
        if record is None or c is None:
            continue
        original_house_key = bookmaker_key(record.get("house") or c.get("house"))
        correction_house_key = bookmaker_key((correction.get("offer") or {}).get("house"))
        if original_house_key and correction_house_key and original_house_key != correction_house_key:
            text = "\n".join([
                "🔵 RECTIFICACIÓN DE CUOTA",
                "",
                f'Partido: {c.get("match")}',
                f'La alerta NO APOSTAR anterior correspondía a {(correction.get("offer") or {}).get("house")} y no a la casa original {record.get("house")}.',
                f'La cuota congelada de la apuesta ya registrada sigue siendo {float(record.get("odds") or c.get("odds")):.2f}.',
                "Para una nueva apuesta se exige revalidar la misma casa.",
                "DINERO REAL MATRIX: BLOQUEADO PARA EJECUCIÓN AUTOMÁTICA",
            ])
            mid = send_telegram(session, token, chat_id, text)
            correction["status"] = "RECTIFICADA_CASA_DISTINTA"
            correction["rectification_message_id"] = mid
            correction["rectified_at_utc"] = now.isoformat()
            rectifications_now += 1

    for key, record in list(sent_by_key.items()):
        c = candidates.get(key)
        if c is None or c.get("sport") != "football" or key in settled_keys:
            continue
        kickoff = parse_dt(c.get("kickoff"))
        if kickoff is None or kickoff <= now:
            continue
        execution = record.get("execution") if isinstance(record.get("execution"), dict) else None
        required_house_key = bookmaker_key(
            (execution or {}).get("bookmaker")
            or record.get("house")
            or c.get("house")
        )
        primary_offer = exact_over25_offer(session, api_key, c["fixture_id"], float(c["p_matrix"]), required_house_key)
        correction_diag: dict[str, Any] = {}
        fallback_offer = odds_api_net_exact_over25_offer(
            session,
            odds_api_net_key,
            str(c["fixture_id"]),
            c.get("kickoff"),
            float(c["p_matrix"]),
            api_key,
            correction_diag,
            required_house_key,
        )
        comparable = [x for x in (primary_offer, fallback_offer) if isinstance(x, dict)]
        offer = max(comparable, key=lambda x: float(x.get("ev") or -999.0)) if comparable else None
        quote_checks += 1
        previous = ledger["quote_state"].get(key) or {}
        sharp_state, sharp_detail = sharp_reference_gate_state(correction_diag)
        if offer is None:
            state = "NO_APOSTAR_SIN_CUOTA_VALIDA_MISMA_CASA"
        elif sharp_state != "PASS_SHARP_REFERENCE_GATE":
            state = "NO_APOSTAR_SIN_REFERENCIA_SHARP_PINNACLE"
        else:
            state = "VERDE" if float(offer["ev"]) > 0 else "NO_APOSTAR"
        ledger["quote_state"][key] = {
            "checked_at_utc": now.isoformat(),
            "fixture_id": c["fixture_id"],
            "required_house_key": required_house_key,
            "state": state,
            "offer": offer,
            "primary_same_house_offer": primary_offer,
            "odds_api_net_same_house_offer": fallback_offer,
            "odds_api_net_diagnostic": correction_diag,
            "sharp_reference_state": sharp_state,
            "sharp_reference_gate": sharp_detail,
            "selected_quote_provider": (offer or {}).get("provider") if isinstance(offer, dict) else None,
        }
        invalid_now = offer is None or float(offer["ev"]) <= 0
        invalid_was_sent = previous.get("state") not in {"NO_APOSTAR", "NO_APOSTAR_SIN_CUOTA_VALIDA_MISMA_CASA"}
        if invalid_now and invalid_was_sent:
            if offer is None:
                correction_text = no_bet_missing_quote_message(c, required_house_key)
            else:
                correction_text = no_bet_message(c, offer)
            mid = send_telegram(session, token, chat_id, correction_text)
            ledger["corrections"].append({
                "signal_key": key,
                "fixture_id": c["fixture_id"],
                "sent_at_utc": now.isoformat(),
                "telegram_message_id": mid,
                "status": "NO_APOSTAR_ENVIADO",
                "offer": offer,
                "reason": state,
            })
            corrections_now += 1

    # Rectify legacy false NO_APOSTAR corrections created when the post-send
    # checker used only API-Football while the send gate had already validated
    # the same authorized house through odds-api.net. Reopen paper exposure only
    # when a fresh same-house revalidation is currently VERDE before kickoff.
    for correction in ledger["corrections"]:
        if correction.get("status") != "NO_APOSTAR_ENVIADO":
            continue
        if correction.get("reason") != "NO_APOSTAR_SIN_CUOTA_VALIDA_MISMA_CASA":
            continue
        key = str(correction.get("signal_key") or "")
        record = sent_by_key.get(key)
        current_quote = ledger["quote_state"].get(key) or {}
        if not isinstance(record, dict) or current_quote.get("state") != "VERDE":
            continue
        kickoff = parse_dt(record.get("kickoff"))
        if kickoff is None or kickoff <= now:
            continue
        current_offer = current_quote.get("offer")
        if not isinstance(current_offer, dict):
            continue
        original_house_key = bookmaker_key(record.get("house"))
        current_house_key = bookmaker_key(current_offer.get("house"))
        if not original_house_key or original_house_key != current_house_key:
            continue
        bet = record.get("paper_bet") if isinstance(record.get("paper_bet"), dict) else None
        correction_lines = [
            "🔵 RECTIFICACIÓN — SEÑAL PREMATCH VIGENTE",
            "",
            f'Partido: {record.get("match")}',
            f'Mercado: {record.get("market")}',
            f'Casa: {record.get("house")}',
            f'Cuota revalidada actual: {float(current_offer.get("odds") or 0):.2f}',
            f'EV revalidado actual: {float(current_offer.get("ev") or 0)*100:+.2f}%',
        ]
        if bet is not None:
            correction_lines += [
                f'Stake MATRIX: STAKE {int(bet.get("stake_level") or 0)}',
                f'Unidades de stake: {float(bet.get("stake_units") or 0):.0f}u',
                f'Apuesta de papel: COP {fmt_cop(bet.get("stake_cop") or 0)}',
            ]
        correction_lines += [
            "La alerta NO APOSTAR anterior fue generada por una ruta de revalidación incompleta que no consultó odds-api.net.",
            "La misma casa vuelve a estar físicamente validada por la ruta multibook gobernada.",
            "La apuesta de papel vuelve a estado ABIERTO.",
            "DINERO REAL MATRIX: BLOQUEADO",
        ]
        correction_text = "\n".join(correction_lines)
        mid = send_telegram(session, token, chat_id, correction_text)
        correction["status"] = "RECTIFICADA_REVALIDACION_MULTIBOOK"
        correction["rectification_message_id"] = mid
        correction["rectified_at_utc"] = now.isoformat()
        correction["rectification_offer"] = current_offer
        correction["rectification_reason"] = "FALSE_NO_BET_API_FOOTBALL_ONLY_PATH"
        bet = record.get("paper_bet")
        if isinstance(bet, dict) and str(bet.get("status") or "").upper() == "CANCELLED_NO_BET":
            bet["status"] = "OPEN"
            bet.pop("cancelled_at_utc", None)
            bet.pop("cancel_reason", None)
            bet.pop("profit_cop", None)
            bet["reopened_at_utc"] = now.isoformat()
            bet["reopen_reason"] = "RECTIFIED_FALSE_NO_BET_MULTIBOOK_SAME_HOUSE"
        rectifications_now += 1

    # One-time stake clarification for already-rectified Telegram messages that
    # predate stake fields in the rectification format.
    for correction in ledger["corrections"]:
        if correction.get("status") != "RECTIFICADA_REVALIDACION_MULTIBOOK":
            continue
        if correction.get("stake_rectification_message_id") is not None:
            continue
        key = str(correction.get("signal_key") or "")
        record = sent_by_key.get(key)
        if not isinstance(record, dict):
            continue
        bet = record.get("paper_bet")
        if not isinstance(bet, dict) or str(bet.get("status") or "").upper() != "OPEN":
            continue
        stake_text = "\n".join([
            "🧪 ACTUALIZACIÓN — STAKE DE LA SEÑAL VIGENTE",
            "",
            f'Partido: {record.get("match")}',
            f'Mercado: {record.get("market")}',
            f'Casa: {record.get("house")}',
            f'Cuota: {float(record.get("odds") or 0):.2f}',
            f'Stake MATRIX: STAKE {int(bet.get("stake_level") or 0)}',
            f'Unidades de stake: {float(bet.get("stake_units") or 0):.0f}u',
            f'Apuesta de papel: COP {fmt_cop(bet.get("stake_cop") or 0)}',
            "Estado: ABIERTO",
            "DINERO REAL MATRIX: BLOQUEADO",
        ])
        mid = send_telegram(session, token, chat_id, stake_text)
        correction["stake_rectification_message_id"] = mid
        correction["stake_rectification_sent_at_utc"] = now.isoformat()

    # Apply any NO_APOSTAR correction created in this same supervisor run immediately,
    # so paper exposure is released before settlement handling.
    post_quote_reconciliation = reconcile_existing_paper_state(ledger, now)
    paper_reconciliation["cancelled_no_bet"] = (
        paper_reconciliation.get("cancelled_no_bet", 0)
        + post_quote_reconciliation.get("cancelled_no_bet", 0)
    )
    paper_reconciliation["settlement_backfills"] = (
        paper_reconciliation.get("settlement_backfills", 0)
        + post_quote_reconciliation.get("settlement_backfills", 0)
    )
    pb = recalc_paper_bankroll(ledger)

    # Enrich already-sent FINAL settlements with any user execution that arrived later in physical evidence.
    for settlement in ledger["settlements"]:
        key = str(settlement.get("signal_key") or "")
        c = candidates.get(key)
        if c is None or settlement.get("actual_stake_cop") is not None:
            continue
        execution = c.get("execution")
        if not isinstance(execution, dict) or execution.get("stake_cop") is None:
            continue
        stake = float(execution["stake_cop"])
        exec_odds = float(execution.get("decimal_odds") or settlement.get("odds") or c.get("odds"))
        actual_profit = stake * (exec_odds - 1.0) if settlement.get("won") else -stake
        settlement["actual_stake_cop"] = stake
        settlement["actual_profit_cop"] = actual_profit
        settlement["execution_evidence_source"] = execution.get("source")
        if settlement.get("economic_update_message_id") is None:
            accum_cop = sum(float(x.get("actual_profit_cop") or 0.0) for x in ledger["settlements"] if x.get("actual_profit_cop") is not None)
            stake_txt = f'{int(stake):,}'.replace(",", ".")
            profit_txt = f'{int(round(actual_profit)):,}'.replace(",", ".")
            accum_txt = f'{int(round(accum_cop)):,}'.replace(",", ".")
            text = "\n".join([
                "💰 ACTUALIZACIÓN ECONÓMICA FINAL",
                "",
                f'Partido: {c.get("match")}',
                f'Estado: {"✅ GANADA" if settlement.get("won") else "❌ PERDIDA"}',
                f'Cuota ejecutada: {exec_odds:.2f}',
                f'Stake registrado: COP {stake_txt}',
                f'Resultado económico: COP {profit_txt}',
                f'Acumulado apuestas registradas: COP {accum_txt}',
                "DINERO REAL MATRIX: BLOQUEADO PARA EJECUCIÓN AUTOMÁTICA",
            ])
            settlement["economic_update_message_id"] = send_telegram(session, token, chat_id, text)
            settlement["economic_update_sent_at_utc"] = now.isoformat()
            economic_updates_now += 1

    for key, record in list(sent_by_key.items()):
        if key in settled_keys or str(record.get("sport") or "football") != "football":
            continue
        paper_bet_guard = record.get("paper_bet")
        if isinstance(paper_bet_guard, dict) and str(paper_bet_guard.get("status") or "").upper() in {"CANCELLED_NO_BET", "VOID_POSTPONED"}:
            continue
        c = candidates.get(key)
        if c is None:
            continue
        kickoff = parse_dt(c.get("kickoff"))
        if kickoff is not None and kickoff > now:
            continue
        final = fixture_final(session, api_key, c["fixture_id"])
        if not final:
            continue
        if final.get("final") is not True:
            if str(final.get("status") or "").upper() in VOID_STATUSES:
                paper_bet = record.get("paper_bet") if isinstance(record.get("paper_bet"), dict) else None
                if paper_enabled and isinstance(paper_bet, dict) and str(paper_bet.get("status") or "").upper() == "OPEN":
                    paper_bet["status"] = "VOID_POSTPONED"
                    paper_bet["voided_at_utc"] = now.isoformat()
                    paper_bet["void_status"] = str(final.get("status") or "").upper()
                    paper_bet["profit_cop"] = 0.0
                    ledger.setdefault("voids", []).append({
                        "signal_key": key,
                        "fixture_id": c["fixture_id"],
                        "match": c["match"],
                        "market": c["market"],
                        "status": str(final.get("status") or "").upper(),
                        "paper_stake_returned_cop": float(paper_bet.get("stake_cop") or 0.0),
                        "voided_at_utc": now.isoformat(),
                    })
            continue
        total = int(final["home_goals"]) + int(final["away_goals"])
        won = total >= 3
        frozen_odds = float(record.get("odds") or c["odds"])
        shadow_profit = frozen_odds - 1.0 if won else -1.0
        execution = record.get("execution") or c.get("execution")
        actual_stake = actual_profit = None
        if isinstance(execution, dict) and execution.get("stake_cop") is not None:
            actual_stake = float(execution["stake_cop"])
            exec_odds = float(execution.get("decimal_odds") or frozen_odds)
            actual_profit = actual_stake * (exec_odds - 1.0) if won else -actual_stake
        paper_bet = record.get("paper_bet") if isinstance(record.get("paper_bet"), dict) else None
        paper_stake = paper_profit = None
        paper_level = None
        if paper_enabled and isinstance(paper_bet, dict) and paper_bet.get("status") == "OPEN":
            paper_stake = float(paper_bet["stake_cop"])
            paper_level = int(paper_bet["stake_level"])
            paper_profit = paper_stake * (frozen_odds - 1.0) if won else -paper_stake
            paper_bet["status"] = "SETTLED"
            paper_bet["settled_at_utc"] = now.isoformat()
            paper_bet["profit_cop"] = paper_profit

        settlement = {
            "signal_key": key,
            "fixture_id": c["fixture_id"],
            "match": c["match"],
            "market": c["market"],
            "final_status": final["status"],
            "home_goals": final["home_goals"],
            "away_goals": final["away_goals"],
            "won": won,
            "odds": frozen_odds,
            "shadow_profit_units": shadow_profit,
            "actual_stake_cop": actual_stake,
            "actual_profit_cop": actual_profit,
            "paper_stake_level": paper_level,
            "paper_stake_cop": paper_stake,
            "paper_profit_cop": paper_profit,
            "settled_at_utc": now.isoformat(),
        }
        projected = ledger["settlements"] + [settlement]
        accum_u = sum(float(x.get("shadow_profit_units") or 0.0) for x in projected)
        accum_cop = sum(float(x.get("actual_profit_cop") or 0.0) for x in projected if x.get("actual_profit_cop") is not None)
        paper_bankroll_after = None
        if paper_profit is not None:
            prior_paper_profit = sum(float(x.get("paper_profit_cop") or 0.0) for x in ledger["settlements"])
            paper_bankroll_after = float(pb["initial_cop"]) + prior_paper_profit + float(paper_profit)
        mid = send_telegram(session, token, chat_id, settlement_message(c, settlement, accum_u, accum_cop, paper_bankroll_after))
        settlement["telegram_message_id"] = mid
        settlement["status"] = "FINAL_ENVIADO_OK"
        ledger["settlements"].append(settlement)
        settled_keys.add(key)
        settlements_now += 1

    pb = recalc_paper_bankroll(ledger)

    blocker_audit = build_blocker_recovery_audit(ledger, candidates, existing_sent_keys, now)
    blocker_summary = blocker_audit.get("summary") or {}

    run_record = {
        "run_at_utc": now.isoformat(),
        "bogota_date": str(today),
        "dates_scanned": dates,
        "football_candidates": len(football),
        "football_watch_candidates": sum(1 for x in football.values() if x.get("watch_candidate") is True),
        "football_existing_sent_candidates": sum(1 for k in football if k in existing_sent_keys),
        "football_unsent_candidates": sum(1 for k in football if k not in existing_sent_keys),
        "tennis_candidates": len(tennis),
        "sent_now": sent_now,
        "delivery_failures_now": delivery_failures_now,
        "quote_checks": quote_checks,
        "pre_send_quote_checks": pre_send_quote_checks,
        "pre_send_waiting_window": pre_send_waiting,
        "pre_send_blocked": pre_send_blocked,
        "pre_send_passed": pre_send_passed,
        "ev_marginal_lab_new_now": ev_lab_new_now,
        "ev_marginal_lab_total_frozen": len(ev_lab["observations"]),
        "monitoring_breaches_now": monitoring_breaches_now,
        "blocker_audit_records": blocker_summary.get("records"),
        "blocker_counts_by_state": blocker_summary.get("counts_by_state"),
        "blocker_counts_by_variable": blocker_summary.get("counts_by_variable"),
        "blocker_counts_by_recoverability": blocker_summary.get("counts_by_recoverability"),
        "corrections_now": corrections_now,
        "rectifications_now": rectifications_now,
        "economic_updates_now": economic_updates_now,
        "settlements_now": settlements_now,
        "total_green_messages": len(ledger["sent"]),
        "total_settlements": len(ledger["settlements"]),
        "duplicate_green_messages_suppressed": max(0, len(candidates) - sent_now),
        "paper_bankroll_enabled": paper_enabled,
        "paper_bets_assigned_now": assigned_paper_now,
        "paper_assignment_updates_now": paper_assignment_updates_now,
        "paper_reconciliation_cancelled_no_bet": paper_reconciliation.get("cancelled_no_bet", 0),
        "paper_reconciliation_settlement_backfills": paper_reconciliation.get("settlement_backfills", 0),
        "paper_bankroll_current_cop": pb.get("current_cop"),
        "paper_open_exposure_cop": pb.get("open_exposure_cop"),
        "paper_open_bets": pb.get("open_bets"),
        "paper_stake_max_level": PAPER_STAKE_MAX_LEVEL,
        "paper_stake_risk_override": PAPER_STAKE_RISK_OVERRIDE,
        "correlated_risk_status": correlated_risk_calibration.get("status"),
        "correlated_risk_sample_records": correlated_risk_calibration.get("sample_records"),
        "correlated_risk_h02_closed": False,
        "real_money": "BLOQUEADO",
    }
    ledger["run_history"].append(run_record)
    ledger["run_history"] = ledger["run_history"][-200:]
    ledger["updated_at_utc"] = now.isoformat()
    ledger["protections"] = {
        "automatic_wagering": False,
        "real_money": "BLOQUEADO",
        "notification_only": True,
        "duplicate_signal_suppression": True,
        "final_only_settlement": True,
        "odds_used_to_generate_probability": False,
        "tennis_fail_closed_until_validated_lane": True,
        "paper_bankroll_simulation_only": True,
        "paper_bankroll_initial_cop": PAPER_BANKROLL_INITIAL_COP,
        "paper_unit_fraction_initial_bankroll": PAPER_UNIT_FRACTION,
        "paper_max_open_exposure_fraction": PAPER_MAX_OPEN_EXPOSURE_FRACTION,
        "green_prematch_revalidation_window_minutes": GREEN_PREMATCH_REVALIDATION_WINDOW_MINUTES,
        "same_house_exact_over25_revalidation_required": True,
        "paper_max_signals_per_league_day": PAPER_MAX_SIGNALS_PER_LEAGUE_DAY,
        "correlated_risk_gate_before_telegram": True,
        "correlated_risk_calibration_status": risk_calibration.status,
        "correlated_risk_evidence_path": str(CORRELATED_RISK_EVIDENCE),
        "correlated_risk_gate": True,
        "correlated_risk_calibration_required": "READY_FAIL_CLOSED",
        "cancel_if_ev_nonpositive_or_exact_quote_missing": True,
    }

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    CORRELATED_RISK_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    BLOCKER_AUDIT_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EV_MARGINAL_LAB_EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    blocker_audit["run_record_reference"] = {
        "run_at_utc": run_record.get("run_at_utc"),
        "football_candidates": run_record.get("football_candidates"),
        "pre_send_waiting_window": run_record.get("pre_send_waiting_window"),
        "pre_send_blocked": run_record.get("pre_send_blocked"),
        "pre_send_passed": run_record.get("pre_send_passed"),
    }
    BLOCKER_AUDIT_EVIDENCE.write_text(
        json.dumps(blocker_audit, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    correlated_risk_evidence = {
        "schema": "MATRIX_CORRELATED_RISK_CALIBRATION_PHYSICAL_PROOF_V1",
        "generated_at_utc": now.isoformat(),
        "ledger_path": str(LEDGER),
        "integration": {
            "pre_telegram_gate": True,
            "fixture_tournament_day_daily_caps": True,
            "fail_closed_missing_metadata": True,
            "flat_1u_preserved": PAPER_STAKE_MAX_LEVEL == 1,
            "p_matrix_modified": False,
            "ev_modified": False,
        },
        "calibration": correlated_risk_calibration,
        "h02_closed": False,
        "h02_blocker": "PAIRWISE_CROSS_MARKET_CORRELATION_NOT_IDENTIFIABLE_FROM_SINGLE_MARKET_TELEGRAM_LEDGER",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    CORRELATED_RISK_EVIDENCE.write_text(
        json.dumps(correlated_risk_evidence, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    band_counts = {"EV_0_2PCT": 0, "EV_2_5PCT": 0}
    for row in ev_lab["observations"]:
        if isinstance(row, dict) and row.get("ev_band") in band_counts:
            band_counts[row["ev_band"]] += 1
    ev_lab["updated_at_utc"] = now.isoformat()
    ev_lab["policy"] = {
        "purpose": "PROSPECTIVE_SHADOW_CALIBRATION_ONLY",
        "minimum_decimal_odds_exclusive": 1.50,
        "p_matrix_minimum": SIGNAL_QUALITY_MIN_P_MATRIX,
        "lab_ev_min_exclusive": EV_MARGINAL_LAB_MIN_EV_EXCLUSIVE,
        "lab_ev_max_exclusive": EV_MARGINAL_LAB_MAX_EV_EXCLUSIVE,
        "production_ev_minimum": SIGNAL_QUALITY_MIN_REVALIDATED_EV,
        "sharp_reference_required": True,
        "correlated_risk_observed_shadow_only": True,
        "p_matrix_mutated_by_odds": False,
        "production_gate_modified": False,
        "telegram_emission": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    ev_lab["summary"] = {
        "frozen_observations": len(ev_lab["observations"]),
        "new_observations_this_run": ev_lab_new_now,
        "remaining_to_300": max(0, EV_MARGINAL_LAB_TARGET_OBSERVATIONS - len(ev_lab["observations"])),
        "target_observations": EV_MARGINAL_LAB_TARGET_OBSERVATIONS,
        "metrics_opened": len(ev_lab["observations"]) >= EV_MARGINAL_LAB_TARGET_OBSERVATIONS,
        "outcomes_read_for_metrics": 0,
        "band_counts": band_counts,
        "status": "ACCUMULATING_PROSPECTIVE_SHADOW",
    }
    EV_MARGINAL_LAB_EVIDENCE.write_text(
        json.dumps(ev_lab, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(run_record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
