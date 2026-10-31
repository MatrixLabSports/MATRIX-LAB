from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def _norm(value: object) -> str:
    s = unicodedata.normalize("NFKD", str(value or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).casefold()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tokens(value: object) -> list[str]:
    return [x for x in _norm(value).split(" ") if x]


def _name_compatible(a: object, b: object) -> bool:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return False
    if na == nb:
        return True

    def abbreviated(full: object, short: object) -> bool:
        f, q = _tokens(full), _tokens(short)
        if len(f) < 2 or len(q) < 2:
            return False
        # Only accept a short leading given-name token; surname tail must be exact.
        if len(q[0]) > 2 or not f[0].startswith(q[0]):
            return False
        return f[1:] == q[1:]

    return abbreviated(a, b) or abbreviated(b, a)


def _tournament_key(value: object) -> str:
    s = _norm(value)
    drop = {
        "itf", "atp", "wta", "men", "women", "singles", "doubles",
        "qualification", "qualifications", "qualifying",
    }
    tokens = [x for x in s.split() if x not in drop and not re.fullmatch(r"[wm]\d+", x)]
    return " ".join(tokens)


def _tournament_compatible(a: object, b: object) -> bool:
    x, y = _tournament_key(a), _tournament_key(b)
    if not x or not y:
        return False
    return x == y or x in y or y in x


def _round_stage(value: object) -> str | None:
    s = _norm(value)
    if not s:
        return None
    if "qualification" in s or "qualifying" in s:
        return "Q"
    # Fractional round labels contain the token "finals"; parse them before
    # the generic final/semi-final branches to avoid 1/16-finals -> F.
    if "1 32 finals" in s or "round of 64" in s:
        return "R64"
    if "1 16 finals" in s or "round of 32" in s:
        return "R32"
    if "1 8 finals" in s or "round of 16" in s:
        return "R16"
    if "quarter" in s or "1 4 finals" in s:
        return "QF"
    if "semi" in s or "1 2 finals" in s:
        return "SF"
    if "final" in s:
        return "F"
    return None


def _parse_time(value: object) -> datetime | None:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _first_rows_by_match(ledger: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in ledger.get("states", []) or []:
        if not isinstance(raw, Mapping):
            continue
        mid = str(raw.get("match_id") or raw.get("provider_event_id") or "").strip()
        if mid and mid not in out:
            out[mid] = dict(raw)
    return out


def _load_ledgers(root: Path, filename: str, provider: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob(f"*/{filename}")):
        try:
            ledger = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        operational_date = str(ledger.get("operational_date_bogota") or path.parent.name)
        for mid, row in _first_rows_by_match(ledger).items():
            if provider == "api_tennis" and "doubles" in str(row.get("event_type") or "").casefold():
                continue
            out.append({
                "provider": provider,
                "operational_date_bogota": operational_date,
                "source_path": str(path),
                "source_sha256": _sha256(path),
                "match_id": mid,
                "p1_name": row.get("p1_name"),
                "p2_name": row.get("p2_name"),
                "tournament": row.get("tournament"),
                "round": row.get("round"),
                "surface": row.get("surface"),
                "gender": row.get("gender"),
                "event_type": row.get("event_type"),
                "captured_at_utc": row.get("captured_at_utc"),
                "settlement_status": row.get("settlement_status"),
                "p1_match_win": row.get("p1_match_win"),
                "quality_state_valid": row.get("quality_state_valid"),
            })
    return out


def build(root: Path, out: Path, max_capture_delta_hours: float = 8.0) -> dict[str, Any]:
    free = _load_ledgers(root, "MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json", "live_tennis_api")
    paid = _load_ledgers(root, "MATRIX_LIVE_TENNIS_API_TENNIS_FAILOVER_LEDGER_V1.json", "api_tennis")

    candidates: list[dict[str, Any]] = []
    for f in free:
        for p in paid:
            if f["operational_date_bogota"] != p["operational_date_bogota"]:
                continue
            if not _tournament_compatible(f["tournament"], p["tournament"]):
                continue

            same = _name_compatible(f["p1_name"], p["p1_name"]) and _name_compatible(f["p2_name"], p["p2_name"])
            reversed_order = _name_compatible(f["p1_name"], p["p2_name"]) and _name_compatible(f["p2_name"], p["p1_name"])
            if not (same or reversed_order):
                continue

            ft, pt = _parse_time(f["captured_at_utc"]), _parse_time(p["captured_at_utc"])
            delta_hours = None if ft is None or pt is None else abs((ft - pt).total_seconds()) / 3600.0
            capture_window_ok = delta_hours is not None and delta_hours <= max_capture_delta_hours

            fr, pr = _round_stage(f["round"]), _round_stage(p["round"])
            round_compatible = fr is None or pr is None or fr == pr

            outcome_compatible: bool | None = None
            if (
                f["settlement_status"] == "FINAL_STANDARD"
                and p["settlement_status"] == "FINAL_STANDARD"
                and f["p1_match_win"] in {0, 1}
                and p["p1_match_win"] in {0, 1}
            ):
                outcome_compatible = (
                    f["p1_match_win"] == p["p1_match_win"]
                    if same
                    else f["p1_match_win"] == 1 - p["p1_match_win"]
                )

            adjudicable = bool(
                capture_window_ok
                and round_compatible
                and outcome_compatible is True
                and str(f.get("surface") or "").strip()
            )
            candidates.append({
                "free_match_id": f["match_id"],
                "paid_match_id": p["match_id"],
                "operational_date_bogota": f["operational_date_bogota"],
                "free_participants": [f["p1_name"], f["p2_name"]],
                "paid_participants": [p["p1_name"], p["p2_name"]],
                "orientation": "SAME" if same else "REVERSED",
                "free_tournament": f["tournament"],
                "paid_tournament": p["tournament"],
                "free_round": f["round"],
                "paid_round": p["round"],
                "free_surface_canonical_binding": f["surface"],
                "capture_delta_hours": delta_hours,
                "capture_window_ok": capture_window_ok,
                "round_compatible": round_compatible,
                "outcome_compatible": outcome_compatible,
                "adjudicable_event_crosswalk": adjudicable,
            })

    adjudicable = [x for x in candidates if x["adjudicable_event_crosswalk"]]
    status = (
        "PASS_EXACT_EVENT_CROSSWALKS_PRESENT"
        if adjudicable
        else "BLOCKED_NO_ADJUDICABLE_CROSS_PROVIDER_OVERLAP"
    )

    source_files = sorted({
        (x["source_path"], x["source_sha256"], x["provider"])
        for x in free + paid
    })
    payload: dict[str, Any] = {
        "schema": "MATRIX_LIVE_TENNIS_CROSS_PROVIDER_EQUIVALENCE_AUDIT_V2",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "status": status,
        "purpose": "Fail-closed event-level cross-provider identity audit. It never authorizes provider-wide calibration merging.",
        "source_files": [
            {"path": p, "sha256": s, "provider": provider}
            for p, s, provider in source_files
        ],
        "counts": {
            "free_unique_match_records_examined": len(free),
            "paid_singles_unique_match_records_examined": len(paid),
            "participant_pair_plus_tournament_same_day_candidates": len(candidates),
            "adjudicable_exact_event_crosswalks": len(adjudicable),
            "states_admitted_to_existing_free_provider_lane": 0,
        },
        "identity_rule": {
            "single_name_join_allowed": False,
            "provider_event_ids_preserved": True,
            "same_operational_date_required": True,
            "both_participants_required": True,
            "tournament_compatibility_required": True,
            "capture_window_required_hours_max": max_capture_delta_hours,
            "round_must_not_conflict": True,
            "final_outcome_orientation_must_agree_when_both_final": True,
            "surface_binding_source_for_crosswalk": "FREE_PROVIDER_EVENT_ONLY_AFTER_EVENT_IDENTITY_IS_ADJUDICATED",
        },
        "candidates": candidates,
        "adjudicable_crosswalks": adjudicable,
        "calibration_admission": {
            "existing_free_provider_lane_mutated": False,
            "paid_only_events_admitted_to_existing_free_provider_lane": False,
            "provider_wide_equivalence_certified": False,
            "reason": (
                "EVENT_LEVEL_CROSSWALKS_DO_NOT_AUTHORIZE_PROVIDER_WIDE_EQUIVALENCE"
                if adjudicable
                else "NO_ADJUDICABLE_CROSS_PROVIDER_OVERLAP_SAMPLE"
            ),
        },
        "operational_resolution": {
            "free_provider_lane": "REMAINS_SEPARATE",
            "paid_provider_native_lane": "CONTINUE_INDEPENDENTLY",
            "automatic_shadow_overlap_probe": "REQUIRED_WHEN_FREE_PRIMARY_HAS_SAME_DAY_LIVE_MATCHES",
            "merge_policy": "FAIL_CLOSED",
        },
        "protections": {
            "missing_not_zero": True,
            "silent_imputation": False,
            "odds_to_probability": False,
            "same_match_train_test_forbidden": True,
            "synthetic_backfill": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    payload["sha256_without_self"] = hashlib.sha256(raw).hexdigest()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="evidence/live_tennis_lab")
    p.add_argument(
        "--out",
        default="evidence/live_tennis_lab/MATRIX_LIVE_TENNIS_CROSS_PROVIDER_EQUIVALENCE_AUDIT_20261012.json",
    )
    p.add_argument("--max-capture-delta-hours", type=float, default=8.0)
    a = p.parse_args()
    result = build(Path(a.root), Path(a.out), a.max_capture_delta_hours)
    print(json.dumps({
        "status": result["status"],
        **result["counts"],
        "merge_policy": result["operational_resolution"]["merge_policy"],
        "real_money": result["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
