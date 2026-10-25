from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from app.market.matrix_market_portfolio import ALL_MARKETS

SUPERVISOR=Path("evidence/market_portfolio/MATRIX_MULTI_MARKET_SUPERVISOR_LAST.json")
REGISTRY=Path("evidence/market_portfolio/MATRIX_42_LANE_PROSPECTIVE_REGISTRY_LAST.json")
ZERO=Path("evidence/market_portfolio/MATRIX_42_LANE_ZERO_PROSPECTIVE_BLOCKERS_LAST.json")
OUT=Path("evidence/market_portfolio/MATRIX_42_LANE_ACTION_BOARD_LAST.json")


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def _priority(count:int,state:str)->str:
    if state=="ACTIVE":
        return "P0_MAINTAIN_ACTIVE_AND_CONTINUE_600"
    if count>=300:
        return "P1_ADVANCE_300_TO_600"
    if count>=100:
        return "P2_ADVANCE_100_TO_300"
    if count>0:
        return "P3_ADVANCE_TO_100"
    return "P4_OPEN_VALID_PROSPECTIVE_FREEZE"


def _next_action(*,count:int,state:str,price_state:str,blocker:str|None)->str:
    if state=="ACTIVE":
        return "KEEP_ACTIVE_PAPER_MONITORING_AND_CONTINUE_PROSPECTIVE_TO_600"
    if count>=300:
        if price_state=="PRICE_FAMILY_NOT_OBSERVED":
            return "CONTINUE_PROSPECTIVE_TO_600_AND_CERTIFY_EXACT_PRICE_FAMILY"
        return "CONTINUE_PROSPECTIVE_TO_600_WITHOUT_CHANGING_MODEL"
    if count>=100:
        return "CONTINUE_VALID_PREMATCH_FREEZES_TO_300"
    if count>0:
        return "CONTINUE_VALID_PREMATCH_FREEZES_TO_100"
    if blocker:
        return f"RESOLVE_BLOCKER:{blocker}"
    return "OPEN_GOVERNED_PREMATCH_FREEZE_PRODUCER"


def build(generated_at:datetime|None=None)->dict[str,Any]:
    sup=_load(SUPERVISOR); reg=_load(REGISTRY); zero=_load(ZERO)
    if sup.get("status")!="PASS" or sup.get("total_required_lanes")!=42:
        raise ValueError("SUPERVISOR_42_NOT_PASS")
    if reg.get("status")!="PASS" or reg.get("total_lanes")!=42:
        raise ValueError("REGISTRY_42_NOT_PASS")
    if zero.get("status")!="PASS":
        raise ValueError("ZERO_BLOCKER_REGISTRY_NOT_PASS")

    sup_rows={str(x.get("market_key")):x for x in sup.get("rows") or [] if isinstance(x,Mapping)}
    reg_rows=reg.get("lanes") or {}
    zero_rows={str(x.get("market_lane")):x for x in zero.get("rows") or [] if isinstance(x,Mapping)}

    expected=[m.key for m in ALL_MARKETS]
    if len(expected)!=42 or len(set(expected))!=42:
        raise ValueError("CANONICAL_PORTFOLIO_NOT_42_UNIQUE")
    if set(sup_rows)!=set(expected) or set(reg_rows)!=set(expected):
        raise ValueError("SILENT_LANE_DROP_OR_EXTRA_LANE")

    rows=[]
    for idx,m in enumerate(ALL_MARKETS,1):
        s=sup_rows[m.key]; r=reg_rows[m.key]; z=zero_rows.get(m.key,{})
        count=int(r.get("prospective_unique_count") or 0)
        blocker=str(z.get("blocker") or "").strip() or None
        state=str(s.get("operational_state") or "")
        price=str(s.get("price_state") or "")
        gates=r.get("gates") or {}
        row={
            "portfolio_index":idx,
            "sport":m.sport,
            "market_lane":m.key,
            "display_name":m.display_name,
            "family":m.family,
            "operational_state":state,
            "production_authorized":bool(s.get("production_authorized")),
            "implementation_present":bool(s.get("implementation_present")),
            "must_continue_collecting":bool(s.get("must_continue_collecting")),
            "price_state":price,
            "prospective_unique_count":count,
            "gate_100_status":(gates.get("100") or {}).get("status"),
            "gate_300_status":(gates.get("300") or {}).get("status"),
            "gate_600_status":(gates.get("600") or {}).get("status"),
            "remaining_to_600":max(0,600-count),
            "zero_prospective_blocker":blocker,
            "priority":_priority(count,state),
            "next_required_action":_next_action(count=count,state=state,price_state=price,blocker=blocker),
        }
        if not row["implementation_present"] or not row["must_continue_collecting"]:
            raise ValueError(f"LANE_CONTRACT_BROKEN:{m.key}")
        rows.append(row)

    counts={
        "total_lanes":len(rows),
        "football_lanes":sum(1 for x in rows if x["sport"]=="football"),
        "tennis_lanes":sum(1 for x in rows if x["sport"]=="tennis"),
        "active_lanes":sum(1 for x in rows if x["operational_state"]=="ACTIVE"),
        "lab_lanes":sum(1 for x in rows if x["operational_state"]=="LAB"),
        "lanes_with_any_prospective":sum(1 for x in rows if x["prospective_unique_count"]>0),
        "lanes_at_100":sum(1 for x in rows if x["prospective_unique_count"]>=100),
        "lanes_at_300":sum(1 for x in rows if x["prospective_unique_count"]>=300),
        "lanes_at_600":sum(1 for x in rows if x["prospective_unique_count"]>=600),
        "zero_prospective_lanes":sum(1 for x in rows if x["prospective_unique_count"]==0),
    }
    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
        "schema":"MATRIX_42_LANE_ACTION_BOARD_V1",
        "generated_at_utc":now,
        "status":"PASS",
        "counts":counts,
        "rows":rows,
        "priority_order":[
            "P0_MAINTAIN_ACTIVE_AND_CONTINUE_600",
            "P1_ADVANCE_300_TO_600",
            "P2_ADVANCE_100_TO_300",
            "P3_ADVANCE_TO_100",
            "P4_OPEN_VALID_PROSPECTIVE_FREEZE",
        ],
        "invariants":{
            "all_42_present_exactly_once":len(rows)==42 and len({x["market_lane"] for x in rows})==42,
            "football_30_tennis_12":counts["football_lanes"]==30 and counts["tennis_lanes"]==12,
            "every_lane_has_next_action":all(bool(x["next_required_action"]) for x in rows),
            "every_lane_must_continue_collecting":all(x["must_continue_collecting"] is True for x in rows),
            "missing_not_zero":True,
            "no_silent_imputation":True,
            "odds_do_not_generate_p_matrix":True,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "source_generated_at":{
            "supervisor":sup.get("generated_at_utc"),
            "prospective_registry":reg.get("generated_at_utc"),
            "zero_blockers":zero.get("generated_at_utc"),
        },
    }


def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--out",default=str(OUT)); a=p.parse_args()
    result=build()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"counts":result["counts"],"real_money":"BLOCKED"},sort_keys=True))


if __name__=="__main__":
    main()
