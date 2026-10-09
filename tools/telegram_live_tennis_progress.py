from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

GATE=Path("evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_CUMULATIVE_GATE_V1.json")
LEDGER=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_LIVE_TENNIS_PROGRESS_LEDGER.json")


def load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def state_payload(gate: dict) -> dict:
    lanes={}
    for name,data in sorted((gate.get("lanes") or {}).items()):
        lanes[name]={
            "usable":int(data.get("settled_quality_valid_unique_match_count") or 0),
            "remaining30":int(((data.get("gates") or {}).get("30") or {}).get("remaining") or 30),
        }
    return {
        "global_unique_match_count":int(gate.get("global_unique_match_count") or 0),
        "final_standard_before_quality":int(gate.get("sum_lane_final_standard_unique_matches_before_quality_gate") or 0),
        "settled_quality_valid":int(gate.get("sum_lane_settled_unique_matches") or 0),
        "ledger_dates_count":int(gate.get("ledger_dates_count") or 0),
        "model_status":str(gate.get("model_status") or ""),
        "probability_output_status":str(gate.get("probability_output_status") or ""),
        "metrics_status":str(gate.get("metrics_status") or ""),
        "lanes":lanes,
    }


def best_lane(state: dict) -> tuple[str,int,int]:
    best=("",-1,30)
    for name,data in state["lanes"].items():
        usable=int(data["usable"])
        rem=int(data["remaining30"])
        if usable>best[1]:
            best=(name,usable,rem)
    return best


def message(state: dict) -> str:
    lane,usable,remaining=best_lane(state)
    lane_label=lane.replace("|"," / ") if lane else "Sin lane válida"
    return (
        "🎾 TENIS LIVE — PROGRESO MATRIX\n"
        f"Partidos live únicos: {state['global_unique_match_count']}\n"
        f"FINAL estándar: {state['final_standard_before_quality']}\n"
        f"FINAL válidos para gates: {state['settled_quality_valid']}\n"
        f"Lane más avanzada: {lane_label} — {usable}/30 (faltan {remaining})\n"
        f"Modelo: {state['model_status']}\n"
        f"Probabilidades: {state['probability_output_status']}\n"
        f"Métricas: {state['metrics_status']}\n"
        "Estado de apuesta: SIN SEÑAL LIVE GOBERNADA\n"
        "REAL_MONEY: BLOQUEADO"
    )


def main() -> None:
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    chat_id=os.environ.get("TELEGRAM_CHAT_ID","").strip()
    if not token or not chat_id:
        raise SystemExit("TELEGRAM_SECRETS_MISSING")

    gate=load(GATE,{})
    if not gate:
        raise SystemExit("LIVE_TENNIS_GATE_MISSING")

    state=state_payload(gate)
    state_hash=hashlib.sha256(
        json.dumps(state,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
    ).hexdigest()

    ledger=load(LEDGER,{"schema":"MATRIX_TELEGRAM_LIVE_TENNIS_PROGRESS_LEDGER_V1","history":[]})
    if ledger.get("last_state_hash")==state_hash:
        print(json.dumps({"status":"SILENT_NO_CHANGE","state_hash":state_hash},sort_keys=True))
        return

    response=requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id":chat_id,"text":message(state)},
        timeout=(10,90),
    )
    try:
        payload=response.json()
    except Exception:
        payload={}
    if response.status_code>=300 or payload.get("ok") is not True:
        raise SystemExit(f"TELEGRAM_LIVE_PROGRESS_SEND_FAILED:{response.status_code}:{payload}")

    mid=int((payload.get("result") or {})["message_id"])
    now=datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    record={
        "sent_at_utc":now,
        "telegram_message_id":mid,
        "state_hash":state_hash,
        **state,
        "notification_type":"LIVE_TENNIS_RESEARCH_PROGRESS",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    ledger["last_state_hash"]=state_hash
    ledger["last_message_id"]=mid
    ledger["updated_at_utc"]=now
    ledger.setdefault("history",[]).append(record)
    ledger["history"]=ledger["history"][-200:]
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    LEDGER.write_text(json.dumps(ledger,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({"status":"SENT","message_id":mid,**state},sort_keys=True))


if __name__=="__main__":
    main()
