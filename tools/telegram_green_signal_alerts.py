from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

BOGOTA = ZoneInfo("America/Bogota")
FOOTBALL_ROOT = Path("evidence/api_football/daily_prematch_reports")
TENNIS_ROOT = Path("evidence/tennis_signals")
LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")

GREEN_STATUSES = {
    "SEÑAL_VERDE_SIMULADA_Y_APUESTA_USUARIO_EJECUTADA",
    "BET_SHADOW_PHYSICAL",
    "SEÑAL_VERDE_SIMULADA",
}
FINAL_STATUSES = {"FT", "AET", "PEN"}
POLICY_BOOKS = {
    "betano": ("betano",),
    "betplay": ("betplay",),
    "bwin": ("bwin",),
    "rushbet": ("rushbet", "rush bet"),
}
MARKET_KEY = "Goles totales Más/Menos"
SELECTION_KEY = "Más de 2.5"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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
                    rows = payload.get("bet_shadow", [])
                    parser = shadow_ev_candidate
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


def exact_over25_offer(session: requests.Session, api_key: str, fixture_id: str, p: float, required_house_key: str | None = None) -> dict[str, Any] | None:
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
    if response.status_code >= 300 or (isinstance(payload, dict) and payload.get("errors") not in ({}, [], None)):
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
                for value in bet.get("values", []) or []:
                    if not isinstance(value, dict) or str(value.get("value") or "").strip().casefold() != "over 2.5":
                        continue
                    dec = odd(value.get("odd"))
                    if dec is None or dec <= 1.50:
                        continue
                    offers.append({
                        "house": str(book.get("name") or ""),
                        "odds": dec,
                        "ev": p * dec - 1.0,
                        "break_even_probability": 1.0 / dec,
                    })
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


def green_message(c: dict[str, Any]) -> str:
    executed = c.get("execution") is not None
    return "\n".join([
        "🟢 SEÑAL VERDE SIMULADA",
        "",
        f'Partido: {c.get("match")}',
        f'Mercado: {c.get("market")}',
        f'P_MATRIX: {float(c["p_matrix"])*100:.2f}%',
        f'Casa: {c.get("house")}',
        f'Cuota física: {float(c["odds"]):.2f}',
        f'EV: {float(c["ev"])*100:+.2f}%',
        f'Hora Bogotá: {fmt_bogota(c.get("kickoff"))}',
        "Estado: PENDIENTE DE RESULTADO FINAL",
        f'Apuesta ejecutada por el usuario: {"SÍ" if executed else "NO"}',
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


def settlement_message(c: dict[str, Any], settlement: dict[str, Any], accum_u: float, accum_cop: float) -> str:
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


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
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
    })
    ledger["schema"] = "MATRIX_TELEGRAM_SIGNAL_LEDGER_V2"
    ledger.setdefault("sent", [])
    ledger.setdefault("quote_state", {})
    ledger.setdefault("corrections", [])
    ledger.setdefault("settlements", [])
    ledger.setdefault("run_history", [])

    session = requests.Session()
    sent_by_key = {str(x.get("signal_key")): x for x in ledger["sent"]}
    settled_keys = {str(x.get("signal_key")) for x in ledger["settlements"]}
    sent_now = corrections_now = settlements_now = quote_checks = 0
    rectifications_now = economic_updates_now = 0
    delivery_failures_now = 0
    ledger.setdefault("delivery_failures", [])

    for key, c in sorted(candidates.items(), key=lambda kv: (str(kv[1].get("kickoff")), kv[0])):
        if key in sent_by_key:
            record = sent_by_key[key]
            for field in ("sport", "fixture_id", "match", "market", "p_matrix", "house", "odds", "ev", "kickoff", "source", "execution"):
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
                "market": c["market"],
                "p_matrix": c["p_matrix"],
                "house": c["house"],
                "odds": c["odds"],
                "ev": c["ev"],
                "kickoff": c["kickoff"],
                "source": c["source"],
                "execution": c.get("execution"),
                "sent_at_utc": now.isoformat(),
                "telegram_message_id": mid,
                "status": "ENVIADO_OK",
                "matrix_real_money": "BLOQUEADO",
            }
            ledger["sent"].append(record)
            sent_by_key[key] = record
            sent_now += 1

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
        offer = exact_over25_offer(session, api_key, c["fixture_id"], float(c["p_matrix"]), required_house_key)
        quote_checks += 1
        previous = ledger["quote_state"].get(key) or {}
        state = "CASA_ORIGINAL_NO_DISPONIBLE_EN_FEED" if required_house_key else "SIN_CUOTA_EXACTA"
        if offer is not None:
            state = "VERDE" if float(offer["ev"]) > 0 else "NO_APOSTAR"
        ledger["quote_state"][key] = {
            "checked_at_utc": now.isoformat(),
            "fixture_id": c["fixture_id"],
            "required_house_key": required_house_key,
            "state": state,
            "offer": offer,
        }
        if offer is not None and float(offer["ev"]) <= 0 and previous.get("state") != "NO_APOSTAR":
            mid = send_telegram(session, token, chat_id, no_bet_message(c, offer))
            ledger["corrections"].append({
                "signal_key": key,
                "fixture_id": c["fixture_id"],
                "sent_at_utc": now.isoformat(),
                "telegram_message_id": mid,
                "status": "NO_APOSTAR_ENVIADO",
                "offer": offer,
            })
            corrections_now += 1

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
        c = candidates.get(key)
        if c is None:
            continue
        kickoff = parse_dt(c.get("kickoff"))
        if kickoff is not None and kickoff > now:
            continue
        final = fixture_final(session, api_key, c["fixture_id"])
        if not final or final.get("final") is not True:
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
            "settled_at_utc": now.isoformat(),
        }
        projected = ledger["settlements"] + [settlement]
        accum_u = sum(float(x.get("shadow_profit_units") or 0.0) for x in projected)
        accum_cop = sum(float(x.get("actual_profit_cop") or 0.0) for x in projected if x.get("actual_profit_cop") is not None)
        mid = send_telegram(session, token, chat_id, settlement_message(c, settlement, accum_u, accum_cop))
        settlement["telegram_message_id"] = mid
        settlement["status"] = "FINAL_ENVIADO_OK"
        ledger["settlements"].append(settlement)
        settled_keys.add(key)
        settlements_now += 1

    run_record = {
        "run_at_utc": now.isoformat(),
        "bogota_date": str(today),
        "dates_scanned": dates,
        "football_candidates": len(football),
        "tennis_candidates": len(tennis),
        "sent_now": sent_now,
        "delivery_failures_now": delivery_failures_now,
        "quote_checks": quote_checks,
        "corrections_now": corrections_now,
        "rectifications_now": rectifications_now,
        "economic_updates_now": economic_updates_now,
        "settlements_now": settlements_now,
        "total_green_messages": len(ledger["sent"]),
        "total_settlements": len(ledger["settlements"]),
        "duplicate_green_messages_suppressed": max(0, len(candidates) - sent_now),
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
    }

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(run_record, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
