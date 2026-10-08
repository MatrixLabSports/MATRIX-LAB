from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

SOURCE = Path("evidence/api_football/daily_prematch_reports/2026-10-08/browser_physical_verification/MATRIX_FOOTBALL_08OCT_BROWSER_PHYSICAL_QUOTES.json")
LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")

GREEN_STATUSES = {
    "SEÑAL_VERDE_SIMULADA_Y_APUESTA_USUARIO_EJECUTADA",
    "BET_SHADOW_PHYSICAL",
    "SEÑAL_VERDE_SIMULADA",
}

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def signal_key(row: dict[str, Any]) -> str:
    market = row.get("physical_market_label") or row.get("user_real_money_execution", {}).get("market") or "Goles totales Más/Menos"
    selection = row.get("physical_selection") or row.get("user_real_money_execution", {}).get("selection") or "Más de 2.5"
    raw = f'{row.get("fixture_id")}|{market}|{selection}'
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def best_quote(row: dict[str, Any]) -> tuple[str, float | None, float | None]:
    house = (
        row.get("best_physically_verified_house")
        or row.get("user_real_money_execution", {}).get("bookmaker")
        or row.get("house")
        or "Casa físicamente verificada"
    )
    odds = (
        row.get("best_physically_verified_decimal_odds")
        or row.get("physical_decimal_odds")
        or row.get("user_real_money_execution", {}).get("decimal_odds")
    )
    ev = row.get("best_physically_verified_ev")
    if ev is None:
        ev = row.get("ev")
    return str(house), float(odds) if odds is not None else None, float(ev) if ev is not None else None

def format_bogota(kickoff: str | None) -> str:
    if not kickoff:
        return "Sin hora"
    try:
        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        return dt.strftime("%d/%m/%Y %I:%M %p")
    except Exception:
        return kickoff

def build_message(row: dict[str, Any]) -> str:
    house, odds, ev = best_quote(row)
    p = row.get("p_matrix_over_2_5")
    executed = bool(row.get("betplay_physical_execution") or row.get("user_real_money_execution"))
    lines = [
        "🟢 SEÑAL VERDE SIMULADA",
        "",
        f'Partido: {row.get("match")}',
        "Mercado: Más de 2.5 goles",
        f'P_MATRIX: {float(p)*100:.2f}%' if p is not None else "P_MATRIX: no disponible",
        f'Casa: {house}',
        f'Cuota física: {float(odds):.2f}' if odds is not None else "Cuota física: no disponible",
        f'EV: {float(ev)*100:+.2f}%' if ev is not None else "EV: no disponible",
        f'Hora Bogotá: {format_bogota(row.get("kickoff_bogota"))}',
        "Estado: PENDIENTE DE RESULTADO FINAL",
        f'Apuesta ejecutada por el usuario: {"SÍ" if executed else "NO"}',
        "DINERO REAL MATRIX: BLOQUEADO",
    ]
    return "\n".join(lines)

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN_NOT_CONFIGURED")
    if not chat_id:
        raise SystemExit("TELEGRAM_CHAT_ID_NOT_CONFIGURED")
    if not SOURCE.exists():
        raise SystemExit(f"SOURCE_NOT_FOUND:{SOURCE}")

    src = load_json(SOURCE, {})
    ledger = load_json(LEDGER, {
        "schema": "MATRIX_TELEGRAM_SIGNAL_LEDGER_V1",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "sent": []
    })
    sent_keys = {str(x.get("signal_key")) for x in ledger.get("sent", [])}
    candidates = [
        r for r in src.get("rows", [])
        if str(r.get("final_shadow_status")) in GREEN_STATUSES
    ]

    sent_now = []
    for row in candidates:
        key = signal_key(row)
        if key in sent_keys:
            continue
        text = build_message(row)
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text},
            timeout=20,
        )
        try:
            payload = response.json()
        except Exception:
            payload = {}
        if response.status_code >= 300 or payload.get("ok") is not True:
            raise SystemExit(f"TELEGRAM_SEND_FAILED:{response.status_code}:{payload}")
        result = payload.get("result") or {}
        record = {
            "signal_key": key,
            "fixture_id": str(row.get("fixture_id")),
            "match": row.get("match"),
            "market": "Más de 2.5 goles",
            "sent_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "telegram_message_id": result.get("message_id"),
            "status": "ENVIADO_OK",
            "matrix_real_money": "BLOQUEADO",
        }
        ledger.setdefault("sent", []).append(record)
        sent_keys.add(key)
        sent_now.append(record)

    ledger["updated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    ledger["source"] = str(SOURCE)
    ledger["protections"] = {
        "automatic_wagering": False,
        "real_money": "BLOQUEADO",
        "notification_only": True,
        "duplicate_signal_suppression": True,
    }
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "candidate_green_signals": len(candidates),
        "sent_now": len(sent_now),
        "already_sent": len(candidates) - len(sent_now),
        "sent_records": sent_now,
        "real_money": "BLOQUEADO",
    }, ensure_ascii=False, sort_keys=True))

if __name__ == "__main__":
    main()
