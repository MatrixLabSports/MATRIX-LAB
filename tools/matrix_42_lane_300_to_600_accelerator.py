from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BOARD=Path("evidence/market_portfolio/MATRIX_42_LANE_ACTION_BOARD_LAST.json")
OUT=Path("evidence/market_portfolio/MATRIX_42_LANE_300_TO_600_ACCELERATOR_LAST.json")


def _load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value


def build(generated_at:datetime|None=None)->dict[str,Any]:
    board=_load(BOARD)
    if board.get("status")!="PASS":
        raise ValueError("ACTION_BOARD_NOT_PASS")
    rows=[x for x in board.get("rows") or [] if isinstance(x,dict)]
    if len(rows)!=42 or len({str(x.get("market_lane")) for x in rows})!=42:
        raise ValueError("ACTION_BOARD_NOT_EXACT_42")

    p1=[
        x for x in rows
        if x.get("priority")=="P1_ADVANCE_300_TO_600"
        and int(x.get("prospective_unique_count") or 0)>=300
        and int(x.get("prospective_unique_count") or 0)<600
    ]
    if not p1:
        selected=[]
        selected_count=None
    else:
        selected_count=max(int(x.get("prospective_unique_count") or 0) for x in p1)
        selected=sorted(
            [x for x in p1 if int(x.get("prospective_unique_count") or 0)==selected_count],
            key=lambda x:int(x.get("portfolio_index") or 9999),
        )

    cohorts=[]
    for count in sorted({int(x.get("prospective_unique_count") or 0) for x in p1}, reverse=True):
        cohort=sorted(
            [x for x in p1 if int(x.get("prospective_unique_count") or 0)==count],
            key=lambda x:int(x.get("portfolio_index") or 9999),
        )
        cohorts.append({
            "prospective_unique_count":count,
            "remaining_to_600":600-count,
            "lane_count":len(cohort),
            "lanes":[str(x.get("market_lane")) for x in cohort],
            "display_names":[str(x.get("display_name")) for x in cohort],
            "price_family_not_observed":[
                str(x.get("market_lane")) for x in cohort
                if x.get("price_state")=="PRICE_FAMILY_NOT_OBSERVED"
            ],
        })

    now=(generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    return {
        "schema":"MATRIX_42_LANE_300_TO_600_ACCELERATOR_V1",
        "generated_at_utc":now,
        "status":"PASS",
        "selection_policy":{
            "scope":"LAB_LANES_WITH_300_TO_599_VALID_PROSPECTIVE",
            "primary_sort":"HIGHEST_PROSPECTIVE_COUNT_FIRST",
            "tie_policy":"ADVANCE_ALL_TIED_LANES_AS_ONE_COHORT",
            "model_refit":False,
            "parameter_search":False,
            "historical_backfill":False,
            "post_start_backfill":False,
            "outcomes_read_to_create_freeze":False,
            "odds_used_to_generate_probability":False,
            "missing_not_zero":True,
            "silent_imputation":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED",
        },
        "selected_cohort":{
            "prospective_unique_count":selected_count,
            "remaining_to_600":None if selected_count is None else 600-selected_count,
            "lane_count":len(selected),
            "lanes":[str(x.get("market_lane")) for x in selected],
            "display_names":[str(x.get("display_name")) for x in selected],
            "required_actions":[str(x.get("next_required_action")) for x in selected],
        },
        "ordered_cohorts":cohorts,
        "portfolio_visibility":{
            "all_42_remain_supervised":True,
            "total_lanes":42,
            "selected_cohort_does_not_suspend_other_lanes":True,
            "zero_prospective_lanes_remain_visible":int((board.get("counts") or {}).get("zero_prospective_lanes") or 0),
        },
        "source_board_generated_at_utc":board.get("generated_at_utc"),
    }


def main()->None:
    p=argparse.ArgumentParser(); p.add_argument("--out",default=str(OUT)); a=p.parse_args()
    result=build()
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "selected_cohort":result["selected_cohort"],
        "real_money":result["selection_policy"]["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
