from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_identity_authority import (
    build_provider_authority_index,
    resolve_authority_mapping,
)

REV_RE = re.compile(r"_R(\d+)\.json$")

PROVIDER_PLAYER_PATTERNS = {
    "api_tennis": re.compile(r"^api-tennis:player:\d+$"),
    "rapidapi_tennis": re.compile(r"^rapidapi-tennis:player:\d+$"),
    "sofascore_browser": re.compile(r"^sofascore:player:\d+$"),
}


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


def _provider_from_player_id(value: object) -> str:
    token = str(value or "")
    if token.startswith("api-tennis:player:"):
        return "api_tennis"
    if token.startswith("rapidapi-tennis:player:"):
        return "rapidapi_tennis"
    if token.startswith("sofascore:player:"):
        return "sofascore_browser"
    return ""


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
    identity_authority: Mapping[str, Any] | None = None,
    supplemental_alias_ledger: Mapping[str, Any] | None = None,
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

    authority_index = build_provider_authority_index(identity_authority)
    supplemental_mappings: dict[str, Mapping[str, Any]] = {}
    if isinstance(supplemental_alias_ledger, Mapping):
        if supplemental_alias_ledger.get("identity_only") is not True:
            raise ValueError("SUPPLEMENTAL_ALIAS_LEDGER_IDENTITY_ONLY_REQUIRED")
        if supplemental_alias_ledger.get("model_admission_forbidden") is not True:
            raise ValueError("SUPPLEMENTAL_ALIAS_LEDGER_MODEL_ADMISSION_GUARD_REQUIRED")
        if supplemental_alias_ledger.get("odds_used") is not False:
            raise ValueError("SUPPLEMENTAL_ALIAS_LEDGER_ODDS_FLAG_INVALID")
        if supplemental_alias_ledger.get("outcomes_used") is not False:
            raise ValueError("SUPPLEMENTAL_ALIAS_LEDGER_OUTCOME_FLAG_INVALID")
        if supplemental_alias_ledger.get("post_cut_competitive_data_used") is not False:
            raise ValueError("SUPPLEMENTAL_ALIAS_LEDGER_POST_CUT_FLAG_INVALID")
        for row in supplemental_alias_ledger.get("mappings", []) or []:
            if not isinstance(row, Mapping) or row.get("status") != "PASS":
                continue
            if row.get("identity_only") is not True or row.get("model_admission_forbidden") is not True:
                continue
            provider_id = str(row.get("provider_player_id") or "")
            canonical_source_id = str(row.get("canonical_source_id") or "")
            canonical_name = str(row.get("canonical_name") or "")
            if not provider_id or not canonical_source_id or not canonical_name:
                continue
            supplemental_mappings[provider_id] = row

    mappings_by_provider: dict[str, dict[str, Any]] = {}
    events: list[dict[str, Any]] = []

    for event in prefeature.get("events", []) or []:
        if not bool(event.get("identity_crosswalk_required")):
            continue
        event_id = str(event.get("event_id") or "")
        event_blockers: list[str] = []
        event_provider_ids: list[str] = []

        identities = list(event.get("player_identities") or [])
        identity_only_mode = (
            prefeature.get("identity_only") is True
            and prefeature.get("model_admission_forbidden") is True
            and event.get("identity_only") is True
            and event.get("model_admission_forbidden") is True
        )
        required_identity_count = 1 if identity_only_mode else 2
        if len(identities) != required_identity_count:
            event_blockers.append(
                "PROVIDER_IDENTITIES_REQUIRED"
                if required_identity_count == 2
                else "IDENTITY_ONLY_PROVIDER_IDENTITY_REQUIRED"
            )

        for identity in identities:
            provider_id = str(identity.get("provider_player_id") or "")
            provider = str(
                identity.get("provider")
                or prefeature.get("discovery_provider")
                or _provider_from_player_id(provider_id)
                or ""
            )
            event_provider_ids.append(provider_id)
            provider_pattern = PROVIDER_PLAYER_PATTERNS.get(provider)
            if provider_pattern is None or not provider_pattern.fullmatch(provider_id):
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
            mapping: dict[str, Any] | None = None
            if len(candidates) == 1:
                candidate = candidates[0]
                provider_name = str(
                    ranking.get("player")
                    or identity.get("display_name")
                    or ""
                ).strip()
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
                    "provider": provider,
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
            else:
                static_blocker = (
                    "STATIC_IDENTITY_NO_MATCH:"
                    if not candidates
                    else "STATIC_IDENTITY_NONUNIQUE:"
                ) + provider_id
                authority_mapping, authority_blocker = resolve_authority_mapping(
                    identity=identity,
                    provider=provider,
                    provider_id=provider_id,
                    ranking=ranking,
                    rank=rank,
                    points=points,
                    authority_index=authority_index,
                )
                if authority_mapping is None:
                    supplemental = supplemental_mappings.get(provider_id)
                    if isinstance(supplemental, Mapping):
                        supplemental_name = str(supplemental.get("provider_display_name") or supplemental.get("canonical_name") or "").strip()
                        supplemental_ioc = str(supplemental.get("canonical_ioc") or "").strip().upper()
                        provider_name = str(ranking.get("player") or identity.get("display_name") or "").strip()
                        provider_ioc = str(ranking.get("country") or "").strip().upper()
                        if (
                            supplemental_name
                            and _norm_name(supplemental_name) in {_norm_name(provider_name), _norm_name(identity.get("display_name"))}
                            and supplemental_ioc == provider_ioc
                            and str(supplemental.get("ranking_cut") or "").replace("-", "") == "20260921"
                        ):
                            mapping = dict(supplemental)
                            mapping["provider"] = provider
                            mapping["provider_player_id"] = provider_id
                            mapping["provider_display_name"] = str(identity.get("display_name") or "")
                            mapping["provider_ranking_name"] = provider_name
                            mapping["provider_rank"] = rank
                            mapping["provider_rank_points"] = points
                            mapping["canonical_rank"] = rank
                            mapping["canonical_rank_points"] = points
                            mapping["match_basis"] = str(mapping.get("match_basis") or "") + "_SUPPLEMENTAL_IDENTITY_ALIAS"
                            mapping["status"] = "PASS"
                        else:
                            event_blockers.append(static_blocker)
                            if authority_index and authority_blocker:
                                event_blockers.append(authority_blocker)
                            continue
                    else:
                        event_blockers.append(static_blocker)
                        if authority_index and authority_blocker:
                            event_blockers.append(authority_blocker)
                        continue
                else:
                    mapping = authority_mapping

            assert mapping is not None

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


def build_all_crosswalks(
    *,
    runtime_dir: Path,
    static_cut_path: Path,
    identity_authority_path: Path | None = None,
) -> dict[str, Any]:
    static_cut = _load(static_cut_path)
    identity_authority = (
        _load(identity_authority_path)
        if identity_authority_path is not None and identity_authority_path.exists()
        else None
    )
    supplemental_alias_path = runtime_dir.parent / "identity" / "MATRIX_CLAY_IDENTITY_ALIAS_LEDGER_LAST.json"
    supplemental_alias_ledger = (
        _load(supplemental_alias_path)
        if supplemental_alias_path.exists()
        else None
    )
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
        result = build_crosswalk(
            prefeature=pre,
            static_cut=static_cut,
            identity_authority=identity_authority,
            supplemental_alias_ledger=supplemental_alias_ledger,
        )
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
        "identity_authority_loaded": identity_authority is not None,
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
    parser.add_argument(
        "--identity-authority",
        default=(
            "evidence/cor0203/identity/"
            "MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R743.json"
        ),
    )
    parser.add_argument("--summary-out", required=True)
    args = parser.parse_args()

    result = build_all_crosswalks(
        runtime_dir=Path(args.runtime_dir),
        static_cut_path=Path(args.static_cut),
        identity_authority_path=Path(args.identity_authority),
    )
    _write(Path(args.summary_out), result)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
