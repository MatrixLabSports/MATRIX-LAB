from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping

GATE_SIZE = 100
BINS = (
    (0.00, 0.50),
    (0.50, 0.60),
    (0.60, 0.70),
    (0.70, 0.75),
    (0.75, 0.80),
    (0.80, 0.85),
    (0.85, 0.90),
    (0.90, 0.95),
    (0.95, 1.0000001),
)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip():
            rows.append(json.loads(raw))
    return rows


def _bin_rows(pairs: Iterable[tuple[float, int]]) -> list[dict[str, Any]]:
    materialized = [(float(p), int(y)) for p, y in pairs]
    out: list[dict[str, Any]] = []
    total_n = len(materialized)
    weighted_gap = 0.0
    max_gap = 0.0
    for lower, upper in BINS:
        bucket = [(p, y) for p, y in materialized if lower <= p < upper]
        if not bucket:
            out.append({
                "lower": lower,
                "upper": min(upper, 1.0),
                "n": 0,
                "mean_probability": None,
                "observed_rate": None,
                "absolute_gap": None,
            })
            continue
        n = len(bucket)
        mean_p = sum(p for p, _ in bucket) / n
        rate = sum(y for _, y in bucket) / n
        gap = abs(mean_p - rate)
        weighted_gap += (n / total_n) * gap
        max_gap = max(max_gap, gap)
        out.append({
            "lower": lower,
            "upper": min(upper, 1.0),
            "n": n,
            "mean_probability": mean_p,
            "observed_rate": rate,
            "absolute_gap": gap,
        })
    return out


def _ece(rows: list[dict[str, Any]]) -> float:
    total = sum(int(r["n"]) for r in rows)
    if total == 0:
        raise ValueError("EMPTY_CALIBRATION_TABLE")
    return sum((int(r["n"]) / total) * float(r["absolute_gap"]) for r in rows if r["n"])


def _mce(rows: list[dict[str, Any]], minimum_bin_n: int = 10) -> float | None:
    powered = [float(r["absolute_gap"]) for r in rows if int(r["n"]) >= minimum_bin_n]
    return max(powered) if powered else None


def _brier_skill(challenger_brier: float, baseline_brier: float) -> float:
    if baseline_brier <= 0:
        raise ValueError("BASELINE_BRIER_MUST_BE_POSITIVE")
    return 1.0 - (challenger_brier / baseline_brier)


def build_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if len(rows) < GATE_SIZE:
        raise ValueError("GATE100_NOT_AVAILABLE")
    gate = rows[:GATE_SIZE]

    one_pairs: list[tuple[float, int]] = []
    over_pairs: list[tuple[float, int]] = []
    btts_pairs: list[tuple[float, int]] = []

    one_brier_ch = one_brier_base = 0.0
    over_brier_ch = over_brier_base = 0.0
    btts_brier_ch = btts_brier_base = 0.0

    for row in gate:
        ch = row["frozen_challenger_probabilities"]
        base = row["frozen_poisson_reference"]
        outcome = row["outcomes"]

        top = max(("H", "D", "A"), key=lambda k: float(ch["1x2"][k]))
        conf = float(ch["1x2"][top])
        one_pairs.append((conf, 1 if outcome["1x2"] == top else 0))

        for klass in ("H", "D", "A"):
            y = 1.0 if outcome["1x2"] == klass else 0.0
            one_brier_ch += (float(ch["1x2"][klass]) - y) ** 2
            one_brier_base += (float(base["1x2"][klass]) - y) ** 2

        p_over = float(ch["over_2_5"])
        p_over_base = float(base["over_2_5"])
        y_over = 1 if bool(outcome["over_2_5"]) else 0
        over_pairs.append((p_over, y_over))
        over_brier_ch += (p_over - y_over) ** 2
        over_brier_base += (p_over_base - y_over) ** 2

        p_btts = float(ch["btts_v2"])
        p_btts_base = float(base["btts"])
        y_btts = 1 if bool(outcome["btts"]) else 0
        btts_pairs.append((p_btts, y_btts))
        btts_brier_ch += (p_btts - y_btts) ** 2
        btts_brier_base += (p_btts_base - y_btts) ** 2

    one_table = _bin_rows(one_pairs)
    over_table = _bin_rows(over_pairs)
    btts_table = _bin_rows(btts_pairs)

    n = float(GATE_SIZE)
    return {
        "schema": "MATRIX_FOOTBALL_CALIBRATION_DIAGNOSTICS_V2",
        "evaluation_sample": "DECLARED_GATE100_PREFIX_ONLY",
        "observations_used": GATE_SIZE,
        "parameter_tuning_allowed": False,
        "high_confidence_policy": "DIAGNOSTIC_ONLY_NOT_A_SELECTION_RULE",
        "markets": {
            "1x2_top_pick": {
                "calibration_bins": one_table,
                "ece": _ece(one_table),
                "mce_min_bin_n_10": _mce(one_table, 10),
                "brier_skill_vs_poisson": _brier_skill(one_brier_ch / n, one_brier_base / n),
            },
            "over_2_5": {
                "calibration_bins": over_table,
                "ece": _ece(over_table),
                "mce_min_bin_n_10": _mce(over_table, 10),
                "brier_skill_vs_poisson": _brier_skill(over_brier_ch / n, over_brier_base / n),
            },
            "btts_v2": {
                "calibration_bins": btts_table,
                "ece": _ece(btts_table),
                "mce_min_bin_n_10": _mce(btts_table, 10),
                "brier_skill_vs_poisson": _brier_skill(btts_brier_ch / n, btts_brier_base / n),
            },
        },
        "governance": {
            "original_357_holdout_reuse_allowed": False,
            "gate100_used_for_tuning": False,
            "p_matrix_status": "NOT_GENERATED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> None:
    root = Path("evidence/api_football")
    rows = _load_jsonl(root / "prospective_calibration/ledger.jsonl")
    diagnostics = build_diagnostics(rows)
    out = root / "prospective_calibration/calibration_diagnostics_v2.json"
    out.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "observations_used": diagnostics["observations_used"],
        "evaluation_sample": diagnostics["evaluation_sample"],
        "real_money": diagnostics["governance"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
