from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

LEDGER=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json")
OUT=Path("evidence/notifications/telegram/MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_LAST.json")


def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("LEDGER_ROOT_MUST_BE_OBJECT")
    return value


def daterange(start:str,end:str):
    d=date.fromisoformat(start); e=date.fromisoformat(end)
    while d<=e:
        yield d.isoformat()
        d+=timedelta(days=1)


def build(ledger:dict[str,Any])->dict[str,Any]:
    pb=ledger.get("paper_bankroll") or {}
    initial=int(pb.get("initial_cop") or 0)
    unit=int(pb.get("unit_cop") or 0)
    if initial<=0 or unit<=0:
        raise ValueError("PAPER_BANKROLL_POLICY_INVALID")

    sent=[x for x in (ledger.get("sent") or []) if isinstance(x,dict)]
    paper=[]
    for s in sent:
        bet=s.get("paper_bet")
        if not isinstance(bet,dict):
            continue
        d=str(bet.get("kickoff_bogota_date") or "")
        if not d:
            raise ValueError(f"PAPER_BET_DATE_MISSING:{s.get('signal_key')}")
        paper.append((d,s,bet))

    if not paper:
        raise ValueError("NO_PAPER_BETS")
    start=min(d for d,_,_ in paper)
    last_bet_date=max(d for d,_,_ in paper)
    ledger_updated_raw=str(ledger.get("updated_at_utc") or "")
    if ledger_updated_raw:
        ledger_updated=datetime.fromisoformat(ledger_updated_raw.replace("Z","+00:00"))
        ledger_bogota_date=ledger_updated.astimezone(ZoneInfo("America/Bogota")).date().isoformat()
        end=max(last_bet_date, ledger_bogota_date)
    else:
        end=last_bet_date
    bankroll=initial
    rows=[]
    seen_signal_keys=set()

    for d in daterange(start,end):
        day=[(s,b) for dd,s,b in paper if dd==d]
        wins=losses=voids=cancelled=excluded=open_count=0
        profit=0.0
        for s,b in day:
            key=str(s.get("signal_key") or "")
            if not key or key in seen_signal_keys:
                raise ValueError(f"DUPLICATE_OR_MISSING_SIGNAL_KEY:{key}")
            seen_signal_keys.add(key)
            status=str(b.get("status") or "")
            p=float(b.get("profit_cop") or 0)
            profit+=p
            if status=="SETTLED":
                if p>0: wins+=1
                elif p<0: losses+=1
                else: raise ValueError(f"SETTLED_ZERO_PROFIT_UNCLASSIFIED:{key}")
            elif status.startswith("VOID"):
                voids+=1
                if abs(p)>0.01: raise ValueError(f"VOID_NONZERO_PROFIT:{key}")
            elif status=="CANCELLED_NO_BET":
                cancelled+=1
                if abs(p)>0.01: raise ValueError(f"CANCELLED_NONZERO_PROFIT:{key}")
            elif status=="EXCLUDED_CANONICAL_AUDIT":
                excluded+=1
                if abs(p)>0.01: raise ValueError(f"EXCLUDED_NONZERO_PROFIT:{key}")
            elif status in {"OPEN","PENDING"}:
                open_count+=1
            else:
                raise ValueError(f"UNKNOWN_PAPER_BET_STATUS:{status}:{key}")

        opening=bankroll
        rounded_profit=int(round(profit))
        bankroll=opening+rounded_profit
        effective=wins+losses
        signals=len(day)
        classified=effective+voids+cancelled+excluded+open_count
        if classified!=signals:
            raise ValueError(f"DAY_CLASSIFICATION_MISMATCH:{d}:{classified}!={signals}")

        rows.append({
            "date_bogota":d,
            "signals":signals,
            "effective_settled":effective,
            "wins":wins,
            "losses":losses,
            "voids":voids,
            "cancelled_no_bet":cancelled,
            "excluded_canonical_audit":excluded,
            "open":open_count,
            "hit_rate_pct":round(100*wins/effective,2) if effective else None,
            "profit_cop":rounded_profit,
            "units":round(rounded_profit/unit,2),
            "bankroll_opening_cop":opening,
            "bankroll_closing_cop":bankroll,
            "continuity_status":"PASS",
        })

    current=int(pb.get("current_cop") or 0)
    if bankroll!=current:
        raise RuntimeError(f"BANKROLL_RECONCILIATION_FAILED:{bankroll}!={current}")
    if rows[0]["bankroll_opening_cop"]!=initial:
        raise RuntimeError("INITIAL_BANKROLL_CONTINUITY_FAILED")
    for prev,cur in zip(rows,rows[1:]):
        if prev["bankroll_closing_cop"]!=cur["bankroll_opening_cop"]:
            raise RuntimeError(f"DAILY_CONTINUITY_FAILED:{prev['date_bogota']}->{cur['date_bogota']}")

    canonical=json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return {
        "schema":"MATRIX_TELEGRAM_DAILY_BANKROLL_CANONICAL_V1",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "source_ledger":"evidence/notifications/telegram/MATRIX_TELEGRAM_SIGNAL_LEDGER.json",
        "source_ledger_updated_at_utc":ledger.get("updated_at_utc"),
        "source_ledger_content_sha256":hashlib.sha256(
            json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")
        ).hexdigest(),
        "policy":{
            "timezone":"America/Bogota",
            "initial_bankroll_cop":initial,
            "unit_cop":unit,
            "one_row_per_calendar_day":True,
            "zero_activity_days_are_preserved":True,
            "wins_losses_derived_from_settled_paper_profit_sign":True,
            "void_cancelled_excluded_must_have_zero_profit":True,
            "daily_bankroll_continuity_required":True,
            "final_bankroll_must_match_source_ledger":True,
            "manual_silent_overwrite_forbidden":True,
            "real_money":"BLOCKED",
        },
        "rows":rows,
        "summary":{
            "first_date_bogota":rows[0]["date_bogota"],
            "last_date_bogota":rows[-1]["date_bogota"],
            "days":len(rows),
            "total_signals":sum(r["signals"] for r in rows),
            "total_effective_settled":sum(r["effective_settled"] for r in rows),
            "total_wins":sum(r["wins"] for r in rows),
            "total_losses":sum(r["losses"] for r in rows),
            "total_voids":sum(r["voids"] for r in rows),
            "total_cancelled_no_bet":sum(r["cancelled_no_bet"] for r in rows),
            "total_excluded_canonical_audit":sum(r["excluded_canonical_audit"] for r in rows),
            "total_profit_cop":sum(r["profit_cop"] for r in rows),
            "total_units":round(sum(r["profit_cop"] for r in rows)/unit,2),
            "current_bankroll_cop":bankroll,
            "ledger_current_bankroll_cop":current,
            "status":"PASS",
            "rows_sha256":hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        },
        "precedence":{
            "daily_table_current_source":"THIS_FILE",
            "raw_economic_source":"MATRIX_TELEGRAM_SIGNAL_LEDGER.json",
            "historical_daily_tables":"REFERENCE_ONLY_SUPERSEDED",
            "memory_or_chat_values":"NEVER_CANONICAL_FOR_CURRENT_TABLE",
        },
    }


def main()->None:
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",default=str(LEDGER))
    p.add_argument("--out",default=str(OUT))
    a=p.parse_args()
    result=build(load(Path(a.ledger)))
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(result["summary"],sort_keys=True))


if __name__=="__main__":
    main()
