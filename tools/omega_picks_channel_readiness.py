from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests

ROOT=Path(__file__).resolve().parents[1]
CFG=ROOT/"config"/"OMEGA_PICKS_TELEGRAM_CHANNELS.json"
OUT=ROOT/"evidence"/"governance"/"OMEGA_PICKS_TELEGRAM_CHANNEL_READINESS_LAST.json"

def tg(session:requests.Session, token:str, method:str, data:dict[str,Any]) -> dict[str,Any]:
    r=session.post(f"https://api.telegram.org/bot{token}/{method}", data=data, timeout=(10,30))
    payload=r.json() if r.content else {}
    if r.status_code>=300 or payload.get("ok") is not True:
        return {"ok":False,"http_status":r.status_code,"description":payload.get("description")}
    return {"ok":True,"result":payload.get("result")}

def main() -> None:
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    token=os.environ.get(cfg["bot"]["token_env"],"").strip()
    now=datetime.now(timezone.utc).replace(microsecond=0)
    result={"schema":"OMEGA_PICKS_TELEGRAM_CHANNEL_READINESS_V1","checked_at_utc":now.isoformat(),"channels":{},"status":"NO_GO"}
    if not token:
        result["blocker"]="TELEGRAM_BOT_TOKEN_NOT_CONFIGURED"
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print(json.dumps(result,ensure_ascii=False))
        return
    s=requests.Session()
    me=tg(s,token,"getMe",{})
    result["bot_getMe"]=me
    bot_id=((me.get("result") or {}).get("id") if me.get("ok") else None)
    all_ok=bool(bot_id)
    for key,ch in cfg["channels"].items():
        chat_id=os.environ.get(ch["env_chat_id"],"").strip()
        row={"expected_name":ch["name"],"expected_visibility":ch["visibility"],"chat_id_configured":bool(chat_id)}
        if not chat_id:
            row["status"]="BLOCKED_CHAT_ID_NOT_CONFIGURED"
            all_ok=False
            result["channels"][key]=row
            continue
        gc=tg(s,token,"getChat",{"chat_id":chat_id})
        row["getChat"]=gc
        if not gc.get("ok"):
            row["status"]="FAIL_GETCHAT"
            all_ok=False
            result["channels"][key]=row
            continue
        info=gc["result"] or {}
        title=str(info.get("title") or "")
        username=info.get("username")
        row["observed"]={"title":title,"type":info.get("type"),"username":username}
        title_ok=title==ch["name"]
        type_ok=info.get("type")==ch["expected_type"]
        public_ok=(bool(username) if ch["requires_public_username"] else True)
        member=tg(s,token,"getChatMember",{"chat_id":chat_id,"user_id":bot_id})
        row["bot_membership"]=member
        status=((member.get("result") or {}).get("status") if member.get("ok") else None)
        admin_ok=status in {"administrator","creator"}
        row["checks"]={"title_ok":title_ok,"type_ok":type_ok,"visibility_ok":public_ok,"bot_admin_ok":admin_ok}
        row["status"]="PASS" if all(row["checks"].values()) else "FAIL"
        if row["status"]!="PASS": all_ok=False
        result["channels"][key]=row
    result["status"]="PASS_READY_FOR_TEST_PUBLICATION" if all_ok else "NO_GO"
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))

if __name__=="__main__":
    main()
