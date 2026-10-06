from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

MIN_SETTLED_MATCHES_PER_LANE = 30
FEATURES_V0_1 = [
    "set_diff_p1",
    "total_game_diff_p1",
    "current_set_game_diff_p1",
    "point_diff_p1",
    "server_is_p1",
    "ranking_advantage_p1",
    "is_tiebreak",
    "age_seconds",
    "observed_age_seconds",
    "corroborated",
    "sources_count",
]


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--readiness",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    readiness=json.loads(Path(args.readiness).read_text(encoding="utf-8"))
    lanes=readiness.get("lanes",{}) or {}

    lane_results={}
    any_open=False
    for lane,data in sorted(lanes.items()):
        settled=int(data.get("settled_unique_match_count") or 0)
        promotable=not lane.startswith("unknown|")
        gate_open=settled>=MIN_SETTLED_MATCHES_PER_LANE and promotable
        any_open=any_open or gate_open
        lane_results[lane]={
            "settled_unique_matches":settled,
            "minimum_required":MIN_SETTLED_MATCHES_PER_LANE,
            "remaining":max(0,MIN_SETTLED_MATCHES_PER_LANE-settled),
            "metadata_lane_promotable":promotable,
            "training_gate":"OPEN" if gate_open else "SEALED",
            "probability_output_gate":"SEALED",
        }

    payload={
        "schema":"MATRIX_LIVE_TENNIS_MODEL_GATE_V0_1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_family_status":"SPECIFIED_NOT_TRAINED",
        "target":"P_LIVE_P1_MATCH_WIN",
        "candidate_feature_set":FEATURES_V0_1,
        "training_unit":"UNIQUE_LIVE_STATE",
        "split_group":"MATCH_ID",
        "minimum_unique_settled_matches_per_lane":MIN_SETTLED_MATCHES_PER_LANE,
        "lane_gates":lane_results,
        "any_lane_training_eligible":any_open,
        "training_executed":False,
        "probability_output_status":"SEALED",
        "metrics_status":"SEALED",
        "required_first_metrics_when_gate_opens":[
            "brier_score",
            "log_loss",
            "ece",
            "auc",
            "calibration_by_probability_band",
            "calibration_by_match_state_band"
        ],
        "protections":{
            "same_match_train_test_forbidden":True,
            "odds_as_model_feature":False,
            "odds_to_probability":False,
            "prematch_model_mutated":False,
            "automatic_wagering":False,
            "real_money":"BLOCKED"
        }
    }

    out=Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":"PASS",
        "any_lane_training_eligible":any_open,
        "training_executed":False,
        "probability_output_status":"SEALED"
    },sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
