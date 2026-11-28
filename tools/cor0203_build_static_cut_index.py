from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any

CUT = 20260921
SIDES = ("winner", "loser")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _number(value: object) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int_number(value: object) -> int | None:
    parsed = _number(value)
    if parsed is None or int(parsed) != parsed:
        return None
    return int(parsed)


def _player_from_row(row: dict[str, str], side: str) -> dict[str, Any] | None:
    player_id = str(row.get(f"{side}_id") or "").strip()
    name = str(row.get(f"{side}_name") or "").strip()
    hand = str(row.get(f"{side}_hand") or "").strip().upper()
    age = _number(row.get(f"{side}_age"))
    rank = _int_number(row.get(f"{side}_rank"))
    points = _int_number(row.get(f"{side}_rank_points"))
    ioc = str(row.get(f"{side}_ioc") or "").strip().upper()

    if not player_id or not name:
        return None
    missing = []
    if hand not in {"R", "L"}:
        missing.append("hand")
    if age is None:
        missing.append("age")
    if rank is None:
        missing.append("rank")
    if points is None:
        missing.append("rank_points")
    if not ioc:
        missing.append("ioc")

    return {
        "canonical_source_id": player_id,
        "canonical_name": name,
        "hand": hand or None,
        "age": age,
        "rank": rank,
        "rank_points": points,
        "ioc": ioc or None,
        "missing": missing,
    }


def build_static_cut_index(csv_path: Path, *, cut: int = CUT) -> dict[str, Any]:
    raw = csv_path.read_bytes()
    rows = list(csv.DictReader(raw.decode("utf-8-sig").splitlines()))
    observations: dict[str, list[dict[str, Any]]] = {}
    exact_rows = 0

    for row in rows:
        try:
            tourney_date = int(float(str(row.get("tourney_date") or "0")))
        except ValueError:
            continue
        if tourney_date != cut:
            continue
        if str(row.get("tourney_level") or "").strip() != "C":
            continue
        exact_rows += 1
        for side in SIDES:
            player = _player_from_row(row, side)
            if player is None:
                continue
            player["tourney_id"] = str(row.get("tourney_id") or "")
            player["tourney_name"] = str(row.get("tourney_name") or "")
            player["surface"] = str(row.get("surface") or "")
            observations.setdefault(player["canonical_source_id"], []).append(player)

    players: dict[str, dict[str, Any]] = {}
    name_index: dict[str, list[str]] = {}
    conflicts: list[dict[str, Any]] = []

    for source_id, items in sorted(observations.items()):
        signatures = {
            (
                item["canonical_name"],
                item["hand"],
                item["age"],
                item["rank"],
                item["rank_points"],
                item["ioc"],
            )
            for item in items
        }
        missing = sorted({field for item in items for field in item["missing"]})
        if len(signatures) != 1 or missing:
            conflicts.append({
                "canonical_source_id": source_id,
                "names": sorted({item["canonical_name"] for item in items}),
                "missing": missing,
                "signature_count": len(signatures),
            })
            continue

        item = items[0]
        record = {
            "canonical_source_id": source_id,
            "canonical_name": item["canonical_name"],
            "hand": item["hand"],
            "age": item["age"],
            "rank": item["rank"],
            "rank_points": item["rank_points"],
            "ioc": item["ioc"],
            "ranking_cut": str(cut),
            "observed_exact_cut": True,
            "source_tournaments": sorted({x["tourney_name"] for x in items}),
            "source_tourney_ids": sorted({x["tourney_id"] for x in items}),
            "source_surfaces": sorted({x["surface"] for x in items}),
            "observation_rows": len(items),
        }
        players[source_id] = record
        name_index.setdefault(item["canonical_name"], []).append(source_id)

    ambiguous_names = {
        name: ids for name, ids in sorted(name_index.items()) if len(ids) != 1
    }
    unique_name_index = {
        name: ids[0] for name, ids in sorted(name_index.items()) if len(ids) == 1
    }

    return {
        "schema": "MATRIX_COR0203_STATIC_CUT_INDEX_V1",
        "ranking_cut": str(cut),
        "source_path": str(csv_path),
        "source_sha256": _sha_bytes(raw),
        "source_rows": len(rows),
        "exact_cut_challenger_rows": exact_rows,
        "players_pass": len(players),
        "players_conflict_or_missing": len(conflicts),
        "players": players,
        "unique_name_index": unique_name_index,
        "ambiguous_names": ambiguous_names,
        "conflicts": conflicts,
        "missing_as_zero": False,
        "silent_imputation": False,
        "post_cut_data_used": False,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--cut", type=int, default=CUT)
    args = parser.parse_args()

    result = build_static_cut_index(Path(args.csv), cut=args.cut)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "ranking_cut": result["ranking_cut"],
        "source_sha256": result["source_sha256"],
        "exact_cut_challenger_rows": result["exact_cut_challenger_rows"],
        "players_pass": result["players_pass"],
        "players_conflict_or_missing": result["players_conflict_or_missing"],
        "ambiguous_names": len(result["ambiguous_names"]),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
