from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_ROOT = Path("evidence/tennis_calendar_physical")
DEFAULT_OUT = Path("evidence/tennis_calendar_reconciliation/MATRIX_TENNIS_WORLD_CALENDAR_RECONCILIATION_LAST.json")

STOP = {
    "tv", "streaming", "directo", "betano", "wplay", "jr",
    "de", "del", "la", "el", "the",
}

def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"EXPECTED_OBJECT:{path}")
    return value

def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).lower()
    value = re.sub(r"[^a-z0-9/ -]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def _tokens(side: str) -> set[str]:
    return {
        tok for tok in re.split(r"[\s/.]+", _fold(side))
        if len(tok) >= 2 and tok not in STOP and not tok.isdigit()
    }

def _flash_pair(name: str) -> tuple[str, str] | None:
    if " - " not in name:
        return None
    left, right = name.split(" - ", 1)
    if not left.strip() or not right.strip():
        return None
    return left.strip(), right.strip()

def _flash_identity(name: str) -> str:
    pair = _flash_pair(name)
    if pair is None:
        return _fold(name)
    return " || ".join(sorted((_fold(pair[0]), _fold(pair[1]))))

def _side_hit(side: str, sofa_raw: str) -> float:
    side_tokens = _tokens(side)
    if not side_tokens:
        return 0.0
    sofa_tokens = _tokens(sofa_raw)
    return len(side_tokens & sofa_tokens) / len(side_tokens)

def _pair_score(left: str, right: str, sofa_raw: str) -> float:
    a = _side_hit(left, sofa_raw)
    b = _side_hit(right, sofa_raw)
    if a < 0.5 or b < 0.5:
        return 0.0
    return (a + b) / 2.0

def _unique(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in values:
        raw = str(raw).strip()
        if not raw:
            continue
        key = _fold(raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    return out

def reconcile(
    sofa: dict[str, Any],
    flash: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    if sofa.get("target_date_bogota") != flash.get("target_date_bogota"):
        raise ValueError("TARGET_DATE_MISMATCH")
    target = str(sofa["target_date_bogota"])
    sofa_obs = _unique(list(sofa.get("observations") or []))
    flash_raw = _unique(list(flash.get("observations") or []))

    flash_obs: list[str] = []
    flash_ids: set[str] = set()
    flash_duplicate_identity_rows = 0
    for raw in flash_raw:
        ident = _flash_identity(raw)
        if ident in flash_ids:
            flash_duplicate_identity_rows += 1
            continue
        flash_ids.add(ident)
        flash_obs.append(raw)

    used_sofa: set[int] = set()
    confirmed: list[dict[str, Any]] = []
    flash_only: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []

    for name in flash_obs:
        pair = _flash_pair(name)
        if pair is None:
            flash_only.append({"flashscore": name, "reason": "FLASH_NAME_NOT_PAIR"})
            continue
        left, right = pair
        scored: list[tuple[float, int]] = []
        for idx, sofa_raw in enumerate(sofa_obs):
            if idx in used_sofa:
                continue
            score = _pair_score(left, right, sofa_raw)
            if score > 0:
                scored.append((score, idx))
        scored.sort(reverse=True)
        if not scored or scored[0][0] < 0.5:
            flash_only.append({
                "flashscore": name,
                "best_score": round(scored[0][0], 6) if scored else 0.0,
                "reason": "NO_CONSERVATIVE_SOFA_IDENTITY_MATCH",
            })
            continue
        best_score, best_idx = scored[0]
        second = scored[1][0] if len(scored) > 1 else 0.0
        if second >= best_score - 0.05:
            ambiguous.append({
                "flashscore": name,
                "best_score": round(best_score, 6),
                "second_score": round(second, 6),
                "reason": "MULTIPLE_NEAR_EQUAL_SOFA_MATCHES",
            })
            continue
        used_sofa.add(best_idx)
        confirmed.append({
            "flashscore": name,
            "sofascore": sofa_obs[best_idx],
            "identity_score": round(best_score, 6),
            "match_basis": "PLAYER_IDENTITY_TOKEN_MATCH_ONLY",
        })

    sofa_only = [
        {"sofascore": raw, "reason": "NO_CONSERVATIVE_FLASH_IDENTITY_MATCH"}
        for idx, raw in enumerate(sofa_obs) if idx not in used_sofa
    ]
    now = (generated_at or datetime.now(timezone.utc)).replace(microsecond=0).isoformat()
    monitoring_total = len(confirmed) + len(sofa_only) + len(flash_only) + len(ambiguous)
    return {
        "schema": "MATRIX_TENNIS_WORLD_CALENDAR_RECONCILIATION_V1",
        "generated_at_utc": now,
        "target_date_bogota": target,
        "status": "PASS_OPEN_RECONCILIATION",
        "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
        "source_counts": {"sofascore": len(sofa_obs), "flashscore": len(flash_obs)},
        "capture_coverage": {
            "sofascore": sofa.get("coverage_claim", "UNKNOWN"),
            "flashscore": flash.get("coverage_claim", "UNKNOWN"),
            "world_complete_certified": False,
        },
        "reconciliation": {
            "confirmed_both": len(confirmed),
            "sofascore_only": len(sofa_only),
            "flashscore_only": len(flash_only),
            "ambiguous": len(ambiguous),
            "monitoring_total": monitoring_total,
            "flash_duplicate_identity_rows_removed": flash_duplicate_identity_rows,
        },
        "confirmed_both": confirmed,
        "sofascore_only": sofa_only,
        "flashscore_only": flash_only,
        "ambiguous": ambiguous,
        "policy": {
            "missing_not_zero": True,
            "no_silent_imputation": True,
            "no_forced_count_equality": True,
            "time_match_certified": False,
            "identity_match_threshold_per_side": 0.5,
            "ambiguous_margin": 0.05,
            "one_to_one_identity_matching": True,
            "odds_generate_p_matrix": False,
            "api_absence_does_not_delete_open_source_event": True,
            "post_start_backfill_forbidden": True,
            "metrics_opened": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }

def _latest_capture_dir(root: Path) -> Path:
    dirs = sorted(path for path in root.iterdir() if path.is_dir())
    if not dirs:
        raise FileNotFoundError("NO_TENNIS_CALENDAR_CAPTURE_DIR")
    return dirs[-1]

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--target-date")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()
    root = Path(args.root)
    day = root / args.target_date if args.target_date else _latest_capture_dir(root)
    sofa = _load(day / "sofascore_opera_capture.json")
    flash = _load(day / "flashscore_opera_capture.json")
    result = reconcile(sofa, flash)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "target_date_bogota": result["target_date_bogota"],
        "source_counts": result["source_counts"],
        "reconciliation": result["reconciliation"],
        "real_money": "BLOCKED",
    }, sort_keys=True))

if __name__ == "__main__":
    main()
