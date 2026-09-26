from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

REV_RE = re.compile(r"_R(\d+)\.json$")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _rev(path: Path) -> int:
    match = REV_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _norm_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _int(value: object) -> int | None:
    try:
        text = str(value).strip()
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def build_crosswalk(
    *,
    prefeature: Mapping[str, Any],
    static_cut: Mapping[str, Any],
) -> dict[str, Any]:
    if str(static_cut.get("ranking_cut")) != "20260921":
        raise ValueError("STATIC_CUT_AUTHORITY_MISMATCH")
    if static_cut.get("silent_imputation") is not False:
        raise ValueError("STATIC_CUT_IMPUTATION_FLAG_INVALID")
    if static_cut.get("post_cut_data_used") is not False:
        raise ValueError("STATIC_CUT_POST_CUT_FLAG_INVALID")

    players = static_cut.get("players")
    if not isinstance(players, Mapping):
        raise ValueError("STATIC_CUT_PLAYERS_INVALID")

    by_rank_points: dict[tuple[int, int], list[Mapping[str, Any]]] = {}
    for source_id, row in players.items():
        if not isinstance(row, Mapping):
            continue
        rank = _int(row.get("rank"))
        points = _int(row.get("rank_points"))
        if rank is None or points is None:
            continue
        payload = dict(row)
        payload["canonical_source_id"] = str(source_id)
        by_rank_points.setdefault((rank, points), []).append(payload)

    mappings_by_provider: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []

    for event in prefeature.get("events", []) or []:
        if not bool(event.get("identity_crosswalk_required")):
            continue
        event_id = str(event.get("event_id") or "")
        event_blockers: list[str] = []
        event_provider_ids: list[str] = []

        identities = list(event.get("player_identities") or [])
        if len(identities) != 2:
            event_blockers.append("PROVIDER_IDENTITIES_REQUIRED")

        for identity in identities:
            provider_id = str(identity.get("provider_player_id") or "")
            event_provider_ids.append(provider_id)
            if not re.fullmatch(r"api-tennis:player:\d+", provider_id):
                event_blockers.append("PROVIDER_PLAYER_ID_INVALID:" + provider_id)
                continue

            ranking = identity.get("provider_ranking")
            if not isinstance(ranking, Mapping):
                event_blockers.append("PROVIDER_RANKING_MISSING:" + provider_id)
                continue

            rank = _int(ranking.get("place"))
            points = _int(ranking.get("points"))
            if rank is None or points is None:
                event_blockers.append("PROVIDER_RANK_POINTS_INVALID:" + provider_id)
                continue

            candidates = by_rank_points.get((rank, points), [])
            if len(candidates) != 1:
                event_blockers.append(
                    ("STATIC_IDENTITY_NO_MATCH:" if not candidates else "STATIC_IDENTITY_NONUNIQUE:")
                    + provider_id
                )
                continue

            candidate = candidates[0]
            provider_name = str(ranking.get("player") or identity.get("display_name") or "").strip()
            display_name = str(identity.get("display_name") or "").strip()
            canonical_name = str(candidate.get("canonical_name") or "").strip()
            canonical_norm = _norm_name(canonical_name)
            provider_norm = _norm_name(provider_name)
            display_norm = _norm_name(display_name)

            if not canonical_norm:
                event_blockers.append("CANONICAL_NAME_MISSING:" + provider_id)
                continue
            if canonical_norm not in {provider_norm, display_norm}:
                event_blockers.append("IDENTITY_NAME_CONFIRMATION_FAIL:" + provider_id)
                continue

            mapping = {
                "provider": "api_tennis",
                "provider_player_id": provider_id,
                "provider_display_name": display_name,
                "provider_ranking_name": provider_name,
                "provider_rank": rank,
                "provider_rank_points": points,
                "canonical_source_id": str(candidate["canonical_source_id"]),
                "canonical_name": canonical_name,
                "canonical_rank": int(candidate["rank"]),
                "canonical_rank_points": int(candidate["rank_points"]),
                "canonical_hand": candidate.get("hand"),
                "canonical_age": candidate.get("age"),
                "canonical_ioc": candidate.get("ioc"),
                "ranking_cut": "20260921",
                "match_basis": "EXACT_RANK_AND_POINTS_PLUS_NAME_CONFIRMATION",
                "status": "PASS",
            }

            existing = mappings_by_provider.get(provider_id)
            if existing is not None and existing["canonical_source_id"] != mapping["canonical_source_id"]:
                event_blockers.append("PROVIDER_ID_CROSSWALK_COLLISION:" + provider_id)
                continue
            mappings_by_provider[provider_id] = mapping

        missing = [
            provider_id
            for provider_id in event_provider_ids
            if provider_id not in mappings_by_provider
        ]
        if missing:
            event_blockers.extend("IDENTITY_CROSSWALK_MISSING:" + value for value in missing)

        events.append({
            "event_id": event_id,
            "provider_player_ids": event_provider_ids,
            "status": "PASS" if not event_blockers else "BLOCKED",
            "blockers": sorted(set(event_blockers)),
        })

    passed_events = sum(1 for row in events if row["status"] == "PASS")
    blocked_events = len(events) - passed_events
    status = (
        "PASS"
        if events and blocked_events == 0
        else "PASS_WITH_BLOCKERS"
        if passed_events and blocked_events
        else "ALL_BLOCKED"
        if events
        else "NO_CROSSWALK_REQUIRED"
    )

    return {
        "schema": "MATRIX_COR0203_IDENTITY_CROSSWALK_V1",
        "revision": prefeature.get("revision"),
        "holdout_id": prefeature.get("holdout_id"),
        "ranking_cut": "20260921",
        "static_cut_source_sha256": static_cut.get("source_sha256"),
        "status": status,
        "events": events,
        "mappings": sorted(
            mappings_by_provider.values(),
            key=lambda row: row["provider_player_id"],
        ),
        "passed_events": passed_events,
        "blocked_events": blocked_events,
        "join_by_name_only": False,
        "silent_identity_join": False,
        "real_money": "BLOCKED",
    }


def build_all_crosswalks(*, runtime_dir: Path, static_cut_path: Path) -> dict[str, Any]:
    static_cut = _load(static_cut_path)
    results: list[dict[str, Any]] = []

    for pre_path in sorted(runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"), key=_rev):
        pre = _load(pre_path)
        required = any(
            bool(event.get("identity_crosswalk_required"))
            for event in pre.get("events", []) or []
        )
        if not required:
            continue

        revision = _rev(pre_path)
        out = runtime_dir / f"MATRIX_COR0203_IDENTITY_CROSSWALK_R{revision}.json"
        result = build_crosswalk(prefeature=pre, static_cut=static_cut)
        result["revision"] = f"R{revision}"
        _write(out, result)
        results.append({
            "revision": revision,
            "status": result["status"],
            "passed_events": result["passed_events"],
            "blocked_events": result["blocked_events"],
            "path": str(out),
        })

    return {
        "schema": "MATRIX_COR0203_IDENTITY_CROSSWALK_SUMMARY_V1",
        "ranking_cut": "20260921",
        "static_cut_source_sha256": static_cut.get("source_sha256"),
        "crosswalk_revisions": results,
        "real_money": "BLOCKED",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--static-cut",
        default="evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json",
    )
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    result = build_all_crosswalks(
        runtime_dir=Path(args.runtime_dir),
        static_cut_path=Path(args.static_cut),
    )
    _write(Path(args.summary_out), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
