from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def build(root: Path, tournament: str, tour: str | None) -> dict[str, Any]:
    wanted_tournament = norm(tournament)
    wanted_tour = norm(tour) if tour else None
    states_by_key: dict[str, dict[str, Any]] = {}
    source_ledgers: list[dict[str, Any]] = []

    for p in sorted(root.glob("20??-??-??/MATRIX_LIVE_TENNIS_STATE_LEDGER_V0_1.json")):
        j = load_json(p)
        matched = 0
        for row in j.get("states") or []:
            if norm(row.get("tournament")) != wanted_tournament:
                continue
            if wanted_tour and norm(row.get("tour")) != wanted_tour:
                continue
            key = str(row.get("state_key") or "")
            if not key:
                continue
            states_by_key[key] = row
            matched += 1
        if matched:
            source_ledgers.append({
                "path": p.as_posix(),
                "generated_at_utc": j.get("generated_at_utc"),
                "matched_state_count": matched,
            })

    states = sorted(
        states_by_key.values(),
        key=lambda x: (
            str(x.get("captured_at_utc") or ""),
            int(x.get("match_id") or 0),
            int(x.get("sequence") or 0),
        ),
    )

    per_match: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in states:
        per_match[str(row.get("match_id"))].append(row)

    matches = []
    final_standard = 0
    pending = 0
    quality_final = 0
    for match_id, rows in sorted(per_match.items(), key=lambda kv: int(kv[0])):
        rows_sorted = sorted(
            rows,
            key=lambda x: (
                str(x.get("captured_at_utc") or ""),
                int(x.get("sequence") or 0),
            ),
        )
        latest = rows_sorted[-1]
        finals = [x for x in rows_sorted if x.get("settlement_status") == "FINAL_STANDARD"]
        labeled = [x for x in rows_sorted if x.get("label_opened") is True]
        quality_valid = any(x.get("quality_state_valid") is True for x in rows_sorted)
        final_row = labeled[-1] if labeled else (finals[-1] if finals else None)
        final_status = bool(finals)
        if final_status:
            final_standard += 1
            if quality_valid:
                quality_final += 1
        else:
            pending += 1
        matches.append({
            "match_id": int(match_id),
            "p1_name": latest.get("p1_name"),
            "p2_name": latest.get("p2_name"),
            "round": latest.get("round"),
            "round_code": latest.get("round_code"),
            "surface": latest.get("surface"),
            "gender": latest.get("gender"),
            "p1_ranking": latest.get("p1_ranking"),
            "p2_ranking": latest.get("p2_ranking"),
            "state_count": len(rows_sorted),
            "first_captured_at_utc": rows_sorted[0].get("captured_at_utc"),
            "last_captured_at_utc": latest.get("captured_at_utc"),
            "latest_sequence": latest.get("sequence"),
            "latest_sets": [latest.get("sets_p1"), latest.get("sets_p2")],
            "latest_games_by_set": [latest.get("games_by_set_p1"), latest.get("games_by_set_p2")],
            "latest_server": latest.get("server"),
            "quality_state_valid_seen": quality_valid,
            "settlement_status": "FINAL_STANDARD" if final_status else "PENDING_FINAL",
            "p1_match_win": None if final_row is None else final_row.get("p1_match_win"),
        })

    payload = {
        "schema": "MATRIX_LIVE_TENNIS_TOURNAMENT_LEDGER_V1",
        "tournament": tournament,
        "tour": tour,
        "source_root": root.as_posix(),
        "source_ledgers": source_ledgers,
        "unique_match_count": len(matches),
        "unique_state_count": len(states),
        "final_standard_match_count": final_standard,
        "quality_valid_final_match_count": quality_final,
        "pending_match_count": pending,
        "matches": matches,
        "states": states,
        "protections": {
            "derived_view_only": True,
            "source_state_rows_not_mutated": True,
            "outcomes_only_from_existing_final_labels": True,
            "probability_output_status": "SEALED",
            "metrics_status": "SEALED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    payload["sha256_without_self"] = hashlib.sha256(raw).hexdigest()
    return payload


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--tournament", required=True)
    ap.add_argument("--tour")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = build(Path(args.root), args.tournament, args.tour)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "tournament": out["tournament"],
        "tour": out["tour"],
        "unique_matches": out["unique_match_count"],
        "unique_states": out["unique_state_count"],
        "final_standard": out["final_standard_match_count"],
        "pending": out["pending_match_count"],
        "sha256_without_self": out["sha256_without_self"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
