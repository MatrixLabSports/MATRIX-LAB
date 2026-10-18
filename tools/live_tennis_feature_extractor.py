from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


POINT_CODE = {"0": 0, "15": 1, "30": 2, "40": 3, "AD": 4, "A": 4}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_with_sha(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def point_code(value: Any) -> int | None:
    token = str(value or "").strip().upper()
    return POINT_CODE.get(token)


def match_metadata(snapshot: dict[str, Any], match_id: int) -> dict[str, Any]:
    for row in snapshot.get("candidates", []) or []:
        if not isinstance(row, dict):
            continue
        match = row.get("match")
        if isinstance(match, dict) and match.get("id") == match_id:
            return match
    selected = snapshot.get("selected")
    if isinstance(selected, dict):
        match = selected.get("match")
        if isinstance(match, dict) and match.get("id") == match_id:
            return match
    raise ValueError(f"MATCH_METADATA_NOT_FOUND:{match_id}")


def derive_state(match: dict[str, Any], snap: dict[str, Any]) -> dict[str, Any]:
    score = snap.get("score") if isinstance(snap.get("score"), dict) else {}
    sets = score.get("sets")
    games = score.get("games")
    points = score.get("points")

    if not (isinstance(sets, list) and len(sets) == 2):
        raise ValueError("SETS_INVALID")
    if not (
        isinstance(games, list)
        and len(games) == 2
        and isinstance(games[0], list)
        and isinstance(games[1], list)
    ):
        raise ValueError("GAMES_INVALID")
    if not (isinstance(points, list) and len(points) == 2):
        raise ValueError("POINTS_INVALID")

    p1_games = [int(x) for x in games[0]]
    p2_games = [int(x) for x in games[1]]
    current_set_index = min(len(p1_games), len(p2_games)) - 1
    current_game_diff = (
        p1_games[current_set_index] - p2_games[current_set_index]
        if current_set_index >= 0
        else None
    )

    p1_rank = match.get("p1_ranking")
    p2_rank = match.get("p2_ranking")
    ranking_advantage_p1 = (
        int(p2_rank) - int(p1_rank)
        if isinstance(p1_rank, int) and isinstance(p2_rank, int)
        else None
    )

    server = score.get("server")
    sequence = score.get("sequence")
    stale = score.get("stale")

    return {
        "provider": "live_tennis_api",
        "match_id": match.get("id"),
        "state_key": f"live_tennis_api:{match.get('id')}:sequence:{sequence}",
        "sequence": sequence,
        "captured_at_utc": snap.get("captured_at_utc"),
        "score_timestamp_utc": score.get("timestamp"),
        "accepted_at_utc": score.get("accepted_at"),
        "response_sha256": snap.get("response_sha256"),
        "tour": match.get("tour"),
        "tournament": match.get("tournament"),
        "round": match.get("round"),
        "round_code": match.get("round_code"),
        "surface": match.get("surface"),
        "p1_name": match.get("p1_name"),
        "p2_name": match.get("p2_name"),
        "p1_ranking": p1_rank,
        "p2_ranking": p2_rank,
        "ranking_advantage_p1": ranking_advantage_p1,
        "sets_p1": int(sets[0]),
        "sets_p2": int(sets[1]),
        "set_diff_p1": int(sets[0]) - int(sets[1]),
        "games_by_set_p1": p1_games,
        "games_by_set_p2": p2_games,
        "total_games_p1": sum(p1_games),
        "total_games_p2": sum(p2_games),
        "total_game_diff_p1": sum(p1_games) - sum(p2_games),
        "current_set_index_zero_based": current_set_index,
        "current_set_game_diff_p1": current_game_diff,
        "point_p1_raw": str(points[0]),
        "point_p2_raw": str(points[1]),
        "point_p1_code": point_code(points[0]),
        "point_p2_code": point_code(points[1]),
        "point_diff_p1": (
            point_code(points[0]) - point_code(points[1])
            if point_code(points[0]) is not None and point_code(points[1]) is not None
            else None
        ),
        "server": server,
        "server_is_p1": True if server == 1 else False if server == 2 else None,
        "is_tiebreak": score.get("is_tiebreak"),
        "deciding_set_rule": (
            (score.get("deciding_set") or {}).get("rule")
            if isinstance(score.get("deciding_set"), dict)
            else None
        ),
        "deciding_set_basis": (
            (score.get("deciding_set") or {}).get("basis")
            if isinstance(score.get("deciding_set"), dict)
            else None
        ),
        "age_seconds": score.get("age_seconds"),
        "observed_age_seconds": score.get("observed_age_seconds"),
        "corroborated": score.get("corroborated"),
        "sources_count": score.get("sources_count"),
        "origin": score.get("origin"),
        "stale": stale,
        "quality_state_valid": (
            snap.get("http_status") == 200
            and isinstance(sequence, int)
            and server in {1, 2}
            and stale is False
            and score.get("origin") == "observed"
        ),
        "p1_match_win": None,
        "settlement_status": "PENDING_FINAL",
        "label_opened": False,
    }


def build_feature_ledger(
    lab_snapshot: dict[str, Any],
    micro_lab: dict[str, Any],
) -> dict[str, Any]:
    match_id = int(micro_lab["match_id"])
    match = match_metadata(lab_snapshot, match_id)
    raw_states = [
        derive_state(match, row)
        for row in micro_lab.get("snapshots", []) or []
        if isinstance(row, dict)
    ]

    by_sequence: dict[int, dict[str, Any]] = {}
    duplicate_rows = 0
    for row in raw_states:
        seq = row["sequence"]
        if not isinstance(seq, int):
            continue
        if seq in by_sequence:
            duplicate_rows += 1
            continue
        by_sequence[seq] = row

    states = [by_sequence[k] for k in sorted(by_sequence)]
    return {
        "schema": "MATRIX_LIVE_TENNIS_FEATURE_LEDGER_V0_1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "model_status": "RESEARCH_ONLY",
        "target": "P_LIVE_P1_MATCH_WIN",
        "observation_unit": "UNIQUE_MATCH_SEQUENCE_STATE",
        "match_id": match_id,
        "raw_snapshot_count": len(raw_states),
        "unique_state_count": len(states),
        "duplicate_transport_snapshots_quarantined": duplicate_rows,
        "states": states,
        "split_rule": "GROUP_BY_MATCH_ID_NO_MATCH_MAY_CROSS_TRAIN_TEST",
        "protections": {
            "prematch_freeze_mutated": False,
            "outcomes_read_during_live_capture": 0,
            "odds_to_probability": False,
            "silent_imputation": False,
            "missing_not_zero": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--lab-snapshot", required=True)
    p.add_argument("--micro-lab", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    lab, lab_sha = load_with_sha(Path(args.lab_snapshot))
    micro, micro_sha = load_with_sha(Path(args.micro_lab))
    result = build_feature_ledger(lab, micro)
    result["source_evidence"] = {
        "lab_snapshot_path": args.lab_snapshot,
        "lab_snapshot_sha256": lab_sha,
        "micro_lab_path": args.micro_lab,
        "micro_lab_sha256": micro_sha,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "PASS",
        "match_id": result["match_id"],
        "raw_snapshot_count": result["raw_snapshot_count"],
        "unique_state_count": result["unique_state_count"],
        "duplicates_quarantined": result["duplicate_transport_snapshots_quarantined"],
        "sequences": [x["sequence"] for x in result["states"]],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
