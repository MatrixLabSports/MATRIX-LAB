from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tools.api_football_over25_forward_validation_100 import (
    _audit_source,
    _binary_metrics,
    _paired_comparison,
)

ROOT = Path("evidence/api_football")
SOURCE_LEDGER = ROOT / "prospective_calibration" / "ledger.jsonl"
SYNC = ROOT / "prospective_calibration" / "sync_last.json"
OUT = ROOT / "calibration_v2" / "MATRIX_OVER25_FULL_CALIBRATION_AUDIT_CURRENT.json"


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise RuntimeError(f"JSONL_ROW_NOT_OBJECT:{path}:{line_no}")
        rows.append(value)
    return rows


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    ).hexdigest()


def main() -> None:
    rows = _load_jsonl(SOURCE_LEDGER)
    sync = _load_json(SYNC)
    _audit_source(rows)

    if len(rows) != int(sync["calibration_observation_count"]):
        raise RuntimeError(
            f"SYNC_LEDGER_COUNT_MISMATCH:{len(rows)}:{sync['calibration_observation_count']}"
        )

    fixture_ids = [str(r["fixture_id"]) for r in rows]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise RuntimeError("DUPLICATE_FIXTURE_ID")

    for row in rows:
        fid = str(row["fixture_id"])
        pc = (row.get("frozen_challenger_probabilities") or {}).get("over_2_5")
        pp = (row.get("frozen_poisson_reference") or {}).get("over_2_5")
        y = (row.get("outcomes") or {}).get("over_2_5")
        if not isinstance(pc, (int, float)):
            raise RuntimeError(f"CHALLENGER_OVER25_MISSING:{fid}")
        if not isinstance(pp, (int, float)):
            raise RuntimeError(f"POISSON_OVER25_MISSING:{fid}")
        if not isinstance(y, bool):
            raise RuntimeError(f"OVER25_OUTCOME_MISSING:{fid}")

    challenger = _binary_metrics(rows, "challenger")
    poisson = _binary_metrics(rows, "poisson")
    paired = _paired_comparison(rows)

    observed = float(challenger["observed_over_2_5_rate"])
    mean_p = float(challenger["mean_predicted_probability"])
    ece = float(challenger["calibration"]["ece"])
    mce = float(challenger["calibration"]["max_calibration_error"])

    brier_ci_support = bool(paired["brier_ci95_excludes_zero_in_favor_of_challenger"])
    logloss_ci_support = bool(paired["log_loss_ci95_excludes_zero_in_favor_of_challenger"])

    if paired["proper_scoring_directional_pass"] and brier_ci_support and logloss_ci_support:
        statistical_verdict = "CHALLENGER_SUPERIOR_ON_FULL_CURRENT_SAMPLE_BY_PAIRED_95CI"
    elif paired["proper_scoring_directional_pass"]:
        statistical_verdict = "DIRECTIONALLY_BETTER_BUT_PAIRED_95CI_NOT_FULLY_CONCLUSIVE"
    else:
        statistical_verdict = "NO_DIRECTIONAL_SUPERIORITY_ON_FULL_CURRENT_SAMPLE"

    result = {
        "schema": "MATRIX_OVER25_FULL_CALIBRATION_AUDIT_V1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "market": "OVER_2_5",
        "scope": "ALL_CURRENT_APPEND_ONLY_PROSPECTIVE_FINAL_CALIBRATION_ROWS",
        "physical_sample": {
            "sample_size": len(rows),
            "unique_fixture_ids": len(set(fixture_ids)),
            "fixture_ids_sha256": _sha256_json(fixture_ids),
            "record_hashes_sha256": _sha256_json([str(r["record_sha256"]) for r in rows]),
            "ledger_hash_chain_verified": True,
            "all_rows_standard_final_ft": True,
            "all_rows_have_challenger_over25_probability": True,
            "all_rows_have_poisson_over25_probability": True,
            "all_rows_have_over25_outcome": True,
            "duplicates": 0,
            "missing_not_zero": True,
            "silent_imputation": False,
        },
        "challenger": challenger,
        "poisson": poisson,
        "paired_comparison": paired,
        "calibration_balance": {
            "mean_predicted_probability": mean_p,
            "observed_over_2_5_rate": observed,
            "observed_minus_predicted_probability": observed - mean_p,
            "ece": ece,
            "max_calibration_error": mce,
            "probability_bands": challenger["probability_band_reliability"],
        },
        "adjudication": {
            "proper_scoring_directional_vs_poisson": "PASS" if paired["proper_scoring_directional_pass"] else "FAIL",
            "paired_uncertainty_brier": "SUPPORTS_CHALLENGER" if brier_ci_support else "INCONCLUSIVE_CI_CROSSES_ZERO",
            "paired_uncertainty_log_loss": "SUPPORTS_CHALLENGER" if logloss_ci_support else "INCONCLUSIVE_CI_CROSSES_ZERO",
            "statistical_verdict": statistical_verdict,
            "model_tuning_authorized": False,
            "recalibration_authorized": False,
            "real_money_decision": "KEEP_BLOCKED",
        },
        "governance": {
            "append_only_source": True,
            "parameter_tuning_allowed": False,
            "refit_allowed": False,
            "model_files_modified": False,
            "odds_used_to_generate_probability": False,
            "outcomes_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "sample_size": len(rows),
        "challenger_brier": challenger["brier_score"],
        "poisson_brier": poisson["brier_score"],
        "challenger_log_loss": challenger["log_loss"],
        "poisson_log_loss": poisson["log_loss"],
        "challenger_ece": ece,
        "challenger_mce": mce,
        "observed_rate": observed,
        "mean_predicted_probability": mean_p,
        "delta_brier": paired["delta_brier_challenger_minus_poisson"],
        "brier_ci95": paired["brier_ci95"],
        "delta_log_loss": paired["delta_log_loss_challenger_minus_poisson"],
        "log_loss_ci95": paired["log_loss_ci95"],
        "statistical_verdict": statistical_verdict,
        "real_money": "BLOCKED",
        "out": str(OUT),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
