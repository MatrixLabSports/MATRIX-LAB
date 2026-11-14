from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from tools.api_football_prospective_calibration import (
    _load_jsonl,
    _sha,
    audit_calibration_ledger,
    compute_metrics,
)

CHECKPOINT=200
REFERENCE_PREFIX=100


def _delta(now: dict[str, Any], prior: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for market in ("1x2", "over_2_5", "btts_v2"):
        out[market] = {
            "challenger_brier_200_minus_100":
                now[market]["challenger"]["brier_score"] - prior[market]["challenger"]["brier_score"],
            "challenger_log_loss_200_minus_100":
                now[market]["challenger"]["log_loss"] - prior[market]["challenger"]["log_loss"],
            "poisson_brier_200_minus_100":
                now[market]["poisson"]["brier_score"] - prior[market]["poisson"]["brier_score"],
            "poisson_log_loss_200_minus_100":
                now[market]["poisson"]["log_loss"] - prior[market]["poisson"]["log_loss"],
            "gate_passed_at_100": bool(prior[market]["gate_passed"]),
            "gate_passed_at_200": bool(now[market]["gate_passed"]),
        }
    out["all_three_markets_pass_at_100"] = bool(prior["all_three_markets_pass"])
    out["all_three_markets_pass_at_200"] = bool(now["all_three_markets_pass"])
    return out


def build_checkpoint(rows: list[dict[str, Any]]) -> dict[str, Any]:
    audit_calibration_ledger(rows)
    n=len(rows)
    base={
        "schema":"MATRIX_FOOTBALL_PROSPECTIVE_CHECKPOINT_200_V1",
        "generated_at_utc":datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "role":"INFORMATIVE_STABILITY_CHECKPOINT_NOT_PROMOTION_GATE",
        "threshold":CHECKPOINT,
        "observations_available":n,
        "parameter_tuning_allowed":False,
        "original_357_holdout_reuse_allowed":False,
        "p_matrix_status":"NOT_GENERATED",
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }
    if n<CHECKPOINT:
        return {
            **base,
            "status":"SEALED_UNTIL_200",
            "remaining":CHECKPOINT-n,
            "metrics_opened":False,
            "metrics":None,
            "stability_100_to_200":None,
            "sample_fixture_ids":None,
            "sample_prefix_sha256":None,
        }

    prefix200=rows[:CHECKPOINT]
    metrics200=compute_metrics(prefix200)
    metrics100=compute_metrics(rows[:REFERENCE_PREFIX])
    return {
        **base,
        "status":"OPENED_AT_200",
        "remaining":0,
        "observations_used":CHECKPOINT,
        "metrics_opened":True,
        "metrics":metrics200,
        "stability_100_to_200":_delta(metrics200,metrics100),
        "sample_fixture_ids":[r["fixture_id"] for r in prefix200],
        "sample_prefix_sha256":_sha([r["record_sha256"] for r in prefix200]),
    }


def main() -> None:
    root=Path("evidence/api_football/prospective_calibration")
    rows=_load_jsonl(root/"ledger.jsonl")
    payload=build_checkpoint(rows)
    root.mkdir(parents=True,exist_ok=True)
    (root/"checkpoint_200.json").write_text(
        json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True)+"\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status":payload["status"],
        "observations_available":payload["observations_available"],
        "metrics_opened":payload["metrics_opened"],
        "real_money":payload["real_money"],
    },sort_keys=True))


if __name__=="__main__":
    main()
