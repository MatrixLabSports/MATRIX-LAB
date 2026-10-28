from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from tools.matrix_premium_cards import render_result_png
from tools.telegram_green_signal_alerts import fixture_final, send_telegram_photo

LEDGER = Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
DELIVERY = Path("evidence/notifications/telegram/MATRIX_PREMIUM_DELIVERY_LEDGER.json")
CARD_ROOT = Path("evidence/notifications/telegram/premium_cards/results")

def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def _caption(record: dict[str, Any], result: dict[str, Any]) -> str:
    state = "✅ GANADA" if result["won"] else "❌ PERDIDA"
    return "\n".join([
        f"OMEGA PICKS PREMIUM — {state}",
        f'Partido: {record.get("match")}',
        f'Resultado final: {result["home_goals"]}-{result["away_goals"]}',
        f'Mercado: {record.get("market")}',
        f'Cuota: {float(record.get("odds") or 0):.2f}',
        "Resultado registrado por OMEGA PICKS.",
    ])

def _supported_result(record: dict[str, Any], final: dict[str, Any]) -> dict[str, Any] | None:
    market = str(record.get("market") or "").casefold()
    if "2.5" not in market or ("más" not in market and "over" not in market):
        return None
    total = int(final["home_goals"]) + int(final["away_goals"])
    return {
        "won": total >= 3,
        "home_goals": int(final["home_goals"]),
        "away_goals": int(final["away_goals"]),
        "odds": float(record.get("odds") or 0),
        "market": record.get("market"),
        "final_status": final.get("status"),
    }

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    premium_chat_id = os.environ.get("MATRIX_PREMIUM_TELEGRAM_CHAT_ID", "").strip()
    api_key = os.environ.get("API_FOOTBALL_KEY", "").strip()
    now = datetime.now(timezone.utc).replace(microsecond=0)

    delivery = _load(DELIVERY, {
        "schema": "MATRIX_PREMIUM_DELIVERY_LEDGER_V1",
        "created_at_utc": now.isoformat(),
        "results": {},
        "run_history": [],
    })
    delivery.setdefault("results", {})
    delivery.setdefault("run_history", [])

    if not premium_chat_id:
        run = {
            "run_at_utc": now.isoformat(),
            "status": "PREMIUM_CHANNEL_NOT_CONFIGURED",
            "checked": 0,
            "sent": 0,
            "real_money": "BLOCKED",
        }
        delivery["run_history"].append(run)
        delivery["run_history"] = delivery["run_history"][-200:]
        DELIVERY.parent.mkdir(parents=True, exist_ok=True)
        DELIVERY.write_text(json.dumps(delivery, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
        print(json.dumps(run, sort_keys=True))
        return
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN_NOT_CONFIGURED")
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")

    ledger = _load(LEDGER, {})
    sent = [x for x in ledger.get("sent", []) if isinstance(x, dict)]
    session = requests.Session()
    checked = sent_now = final_not_ready = unsupported = failures = 0

    for record in sent:
        key = str(record.get("signal_key") or "")
        if not key or record.get("premium_card_version") != "MATRIX_PREMIUM_CARD_V1":
            continue
        if record.get("premium_pick_message_id") is None:
            continue
        if key in delivery["results"] and delivery["results"][key].get("telegram_message_id") is not None:
            continue
        checked += 1
        final = fixture_final(session, api_key, str(record.get("fixture_id") or ""))
        if not final or final.get("final") is not True:
            final_not_ready += 1
            continue
        result = _supported_result(record, final)
        if result is None:
            unsupported += 1
            continue
        path = CARD_ROOT / f"{key}.png"
        meta = render_result_png(record, result, key, path)
        try:
            mid = send_telegram_photo(session, token, premium_chat_id, path, _caption(record, result))
        except Exception as exc:
            delivery["results"][key] = {
                "signal_key": key,
                "fixture_id": record.get("fixture_id"),
                "status": "DELIVERY_FAILED_RETRY_NEXT_RUN",
                "error": str(exc)[:500],
                "rendered_image_path": str(path),
                "fingerprint": meta["fingerprint"],
                "attempted_at_utc": now.isoformat(),
            }
            failures += 1
            continue
        delivery["results"][key] = {
            "signal_key": key,
            "fixture_id": record.get("fixture_id"),
            "match": record.get("match"),
            "market": record.get("market"),
            **result,
            "rendered_image_path": str(path),
            "fingerprint": meta["fingerprint"],
            "telegram_message_id": mid,
            "sent_at_utc": now.isoformat(),
            "status": "FINAL_PREMIUM_SENT_OK",
        }
        sent_now += 1

    run = {
        "run_at_utc": now.isoformat(),
        "status": "PASS",
        "checked": checked,
        "sent": sent_now,
        "final_not_ready": final_not_ready,
        "unsupported_market": unsupported,
        "delivery_failures": failures,
        "polling_interval_target_minutes": 5,
        "odds_provider_calls": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    delivery["updated_at_utc"] = now.isoformat()
    delivery["run_history"].append(run)
    delivery["run_history"] = delivery["run_history"][-200:]
    DELIVERY.parent.mkdir(parents=True, exist_ok=True)
    DELIVERY.write_text(json.dumps(delivery, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(run, sort_keys=True))

if __name__ == "__main__":
    main()
