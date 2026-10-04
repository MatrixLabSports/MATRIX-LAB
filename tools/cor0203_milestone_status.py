from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

MILESTONES=(100,150,200)


def build_status(uniqueness: dict[str,Any]) -> dict[str,Any]:
    count=int(uniqueness.get("unique_calibration_observations") or 0)
    result=str(uniqueness.get("result") or "")
    if result!="PASS":
        raise ValueError("UNIQUENESS_NOT_PASS")
    gates={}
    for threshold in MILESTONES:
        reached=count>=threshold
        gates[str(threshold)]={
            "threshold":threshold,
            "status":"REACHED" if reached else "PENDING",
            "current_unique_observations":count,
            "remaining":max(0,threshold-count),
            "metrics_open_allowed":False,
        }
    return {
        "schema":"MATRIX_COR0203_MILESTONE_STATUS_V1",
        "unique_calibration_observations":count,
        "window1_target":200,
        "total_target":600,
        "remaining_to_200":max(0,200-count),
        "remaining_to_600":max(0,600-count),
        "milestones":gates,
        "window1_physical_status":"CLOSED_AT_200" if count>=200 else "ACCUMULATING",
        "metrics_policy":"SEALED_UNTIL_600",
        "metrics_opened":False,
        "outcomes_read_for_metrics":0,
        "parameter_tuning_allowed":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
        "integrity_result":"PASS",
    }


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("--uniqueness",required=True)
    p.add_argument("--out",required=True)
    args=p.parse_args()
    uniqueness=json.loads(Path(args.uniqueness).read_text(encoding="utf-8"))
    payload=build_status(uniqueness)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps({
        "count":payload["unique_calibration_observations"],
        "m100":payload["milestones"]["100"]["status"],
        "m150":payload["milestones"]["150"]["status"],
        "m200":payload["milestones"]["200"]["status"],
        "metrics_opened":False,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
