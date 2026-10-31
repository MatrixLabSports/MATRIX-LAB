from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRIORITY_MARKETS = (
    "TEAM_TOTAL_GOALS_HOME",
    "TEAM_TOTAL_GOALS_AWAY",
    "DOUBLE_CHANCE_12",
    "ASIAN_OR_EUROPEAN_HANDICAP",
)


def _load(path: Path) -> dict[str, Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict):
        raise ValueError("CATALOG_ROOT_NOT_OBJECT")
    return value


def build(catalog: dict[str, Any], *, target_date_bogota: str) -> dict[str, Any]:
    matches=catalog.get("matches") or {}
    rows=[]
    for key in PRIORITY_MARKETS:
        observed=matches.get(key) or []
        rows.append({
            "market_key":key,
            "catalog_match_count":len(observed),
            "catalog_matches":observed,
            "lab_state":"LAB_PRICE_COVERAGE_ACTIVE" if observed else "BLOCKED_PRICE_FAMILY",
            "probability_status":"NOT_GENERATED",
            "p_matrix_status":"NOT_GENERATED",
            "p_sharp_status":"NOT_GENERATED",
            "outcomes_read_for_model":0,
            "must_continue_collecting":True,
        })
    active=sum(1 for x in rows if x["lab_state"]=="LAB_PRICE_COVERAGE_ACTIVE")
    return {
        "schema":"MATRIX_API_FOOTBALL_PRIORITY_MARKET_LAB_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "target_date_bogota":target_date_bogota,
        "priority_markets":list(PRIORITY_MARKETS),
        "rows":rows,
        "active_price_coverage_labs":active,
        "blocked_price_labs":len(rows)-active,
        "purpose":"PRICE_AND_MARKET_BINDING_ACCUMULATION_ONLY",
        "odds_used_to_generate_p_matrix":False,
        "silent_probability_imputation":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "status":"PASS",
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--catalog",required=True)
    p.add_argument("--target-date-bogota",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    result=build(_load(Path(a.catalog)),target_date_bogota=a.target_date_bogota)
    out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":result["status"],
        "active_price_coverage_labs":result["active_price_coverage_labs"],
        "blocked_price_labs":result["blocked_price_labs"],
        "real_money":result["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
