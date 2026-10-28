from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

LEDGER=Path("evidence/notifications/telegram/MATRIX_MEMBERSHIP_LEDGER.json")
AUDIT=Path("evidence/governance/MATRIX_MEMBERSHIP_GUARD_LAST.json")

def _load(path:Path, default:Any)->Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def parse_dt(value:Any):
    if not value:
        return None
    try:
        dt=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def membership_state(record:dict[str,Any], now:datetime)->str:
    if str(record.get("payment_status") or "").upper()!="VERIFIED":
        return "PENDING_PAYMENT"
    exp=parse_dt(record.get("expires_at_utc"))
    if exp is None:
        return "INVALID_EXPIRY"
    seconds=(exp-now).total_seconds()
    if seconds<=0:
        return "EXPIRED"
    if seconds<=24*3600:
        return "EXPIRING_24H"
    if seconds<=48*3600:
        return "EXPIRING_48H"
    return "ACTIVE"

def telegram_call(session:requests.Session, token:str, method:str, data:dict[str,Any])->dict[str,Any]:
    r=session.post(f"https://api.telegram.org/bot{token}/{method}",data=data,timeout=(10,30))
    try:
        payload=r.json()
    except Exception:
        payload={}
    if r.status_code>=300 or payload.get("ok") is not True:
        raise RuntimeError(f"TELEGRAM_{method}_FAILED:{r.status_code}:{payload}")
    return payload

def remove_member(session:requests.Session, token:str, chat_id:str, user_id:int)->None:
    telegram_call(session,token,"banChatMember",{"chat_id":chat_id,"user_id":user_id,"revoke_messages":"true"})
    telegram_call(session,token,"unbanChatMember",{"chat_id":chat_id,"user_id":user_id,"only_if_banned":"true"})

def main()->None:
    token=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
    premium_chat=os.environ.get("MATRIX_PREMIUM_TELEGRAM_CHAT_ID","").strip()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    ledger=_load(LEDGER,{"schema":"MATRIX_MEMBERSHIP_LEDGER_V1","members":[]})
    members=ledger.setdefault("members",[])
    session=requests.Session()
    removed=0
    pending_removal=0
    invalid=0
    for row in members:
        if not isinstance(row,dict):
            continue
        state=membership_state(row,now)
        row["computed_state"]=state
        row["last_checked_at_utc"]=now.isoformat()
        if state=="INVALID_EXPIRY":
            invalid+=1
            continue
        if state!="EXPIRED" or row.get("removed_at_utc"):
            continue
        if not token or not premium_chat or row.get("telegram_user_id") is None:
            row["removal_status"]="PENDING_CONFIGURATION_OR_USER_ID"
            pending_removal+=1
            continue
        remove_member(session,token,premium_chat,int(row["telegram_user_id"]))
        row["removed_at_utc"]=now.isoformat()
        row["removal_status"]="REMOVED_FROM_PREMIUM"
        removed+=1
    LEDGER.parent.mkdir(parents=True,exist_ok=True)
    LEDGER.write_text(json.dumps(ledger,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    audit={
        "schema":"MATRIX_MEMBERSHIP_GUARD_AUDIT_V1",
        "checked_at_utc":now.isoformat(),
        "members":len(members),
        "removed_now":removed,
        "pending_removal":pending_removal,
        "invalid_expiry":invalid,
        "telegram_configured":bool(token and premium_chat),
        "removal_method":"banChatMember_then_unbanChatMember",
        "real_money":"BLOCKED"
    }
    AUDIT.parent.mkdir(parents=True,exist_ok=True)
    AUDIT.write_text(json.dumps(audit,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(audit,sort_keys=True))

if __name__=="__main__":
    main()
