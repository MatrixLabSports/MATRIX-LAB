from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import unicodedata
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient

CUT_TOKEN = "20260921"
CUT_DATE = date(2026, 9, 21)
PLAYER_RE = re.compile(r"^rapidapi-tennis:player:(\d+)$")
PREF_RE = re.compile(r"_R(\d+)\.json$")


def _norm_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _canonical_ioc(value: object, aliases: Mapping[str, Any]) -> str:
    token = str(value or "").strip().upper()
    return str(aliases.get(token, token)).strip().upper()


def _hand_from_profile(value: object) -> str | None:
    token = str(value or "").strip().casefold()
    if token.startswith("right"):
        return "R"
    if token.startswith("left"):
        return "L"
    return None


def _dob_token(value: object) -> str | None:
    token = str(value or "").strip()
    if len(token) < 10:
        return None
    raw = token[:10].replace("-", "")
    if len(raw) != 8 or not raw.isdigit():
        return None
    try:
        parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except ValueError:
        return None
    if parsed >= CUT_DATE:
        return None
    return raw


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def _rev(path: Path) -> int:
    match = PREF_RE.search(path.name)
    return int(match.group(1)) if match else -1


def _static_resolves(identity: Mapping[str, Any], static_cut: Mapping[str, Any]) -> bool:
    ranking = identity.get("provider_ranking")
    if not isinstance(ranking, Mapping):
        return False
    try:
        rank = int(str(ranking.get("place") or "").strip())
        points = int(str(ranking.get("points") or "").strip())
    except ValueError:
        return False
    candidates = []
    for source_id, row in (static_cut.get("players") or {}).items():
        if not isinstance(row, Mapping):
            continue
        try:
            row_rank = int(row.get("rank"))
            row_points = int(row.get("rank_points"))
        except (TypeError, ValueError):
            continue
        if (row_rank, row_points) == (rank, points):
            candidates.append((str(source_id), row))
    if len(candidates) != 1:
        return False
    name = str(identity.get("display_name") or ranking.get("player") or "").strip()
    return _norm_name(candidates[0][1].get("canonical_name")) == _norm_name(name)


def _candidate_identities(
    *,
    runtime_dir: Path,
    authority: Mapping[str, Any],
    static_cut: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    known = {
        str(row.get("provider_player_id") or "")
        for row in authority.get("records", []) or []
        if isinstance(row, Mapping)
    }
    seen: dict[str, dict[str, Any]] = {}
    conflicts: list[dict[str, Any]] = []

    for path in sorted(runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json"), key=_rev):
        payload = _load(path)
        for event in payload.get("events", []) or []:
            if not isinstance(event, Mapping) or not event.get("identity_crosswalk_required"):
                continue
            for identity in event.get("player_identities", []) or []:
                if not isinstance(identity, Mapping):
                    continue
                provider_id = str(identity.get("provider_player_id") or "")
                match = PLAYER_RE.fullmatch(provider_id)
                if not match or provider_id in known or _static_resolves(identity, static_cut):
                    continue
                ranking = identity.get("provider_ranking")
                if not isinstance(ranking, Mapping):
                    continue
                snapshot = str(ranking.get("snapshot_date") or "").replace("-", "")
                if snapshot != CUT_TOKEN:
                    continue
                display_name = str(identity.get("display_name") or "").strip()
                ranking_name = str(ranking.get("player") or display_name).strip()
                country = str(ranking.get("country") or "").strip().upper()
                if not display_name or _norm_name(display_name) != _norm_name(ranking_name) or not country:
                    continue
                row = {
                    "provider_player_id": provider_id,
                    "numeric_player_id": match.group(1),
                    "display_name": display_name,
                    "ranking_name": ranking_name,
                    "provider_ioc_raw": country,
                    "provider_rank": str(ranking.get("place") or "").strip(),
                    "provider_rank_points": str(ranking.get("points") or "").strip(),
                    "ranking_cut": "2026-09-21",
                    "source_prefeature": path.name,
                    "source_event_id": str(event.get("event_id") or ""),
                }
                old = seen.get(provider_id)
                signature = (
                    _norm_name(display_name),
                    country,
                    row["provider_rank"],
                    row["provider_rank_points"],
                )
                if old is not None:
                    old_signature = (
                        _norm_name(old["display_name"]),
                        old["provider_ioc_raw"],
                        old["provider_rank"],
                        old["provider_rank_points"],
                    )
                    if signature != old_signature:
                        conflicts.append({
                            "provider_player_id": provider_id,
                            "reason": "PREFEATURE_IDENTITY_CONFLICT",
                            "first": old_signature,
                            "second": signature,
                        })
                    continue
                seen[provider_id] = row
    return list(seen.values()), conflicts


def _history_index(
    history_csv: Path,
    *,
    aliases: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    rows = list(csv.DictReader(history_csv.read_text(encoding="utf-8-sig").splitlines()))
    grouped: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "canonical_source_ids": set(),
            "canonical_iocs": set(),
            "observed_hands": set(),
            "rows": 0,
            "latest_row_date": 0,
            "canonical_names": set(),
        }
    )
    for row in rows:
        try:
            tourney_date = int(float(str(row.get("tourney_date") or "0")))
        except ValueError:
            continue
        if tourney_date >= 20260921:
            continue
        if str(row.get("tourney_level") or "").strip() != "C":
            continue
        for side in ("winner", "loser"):
            name = str(row.get(f"{side}_name") or "").strip()
            source_id = str(row.get(f"{side}_id") or "").strip()
            ioc = _canonical_ioc(row.get(f"{side}_ioc"), aliases)
            hand = str(row.get(f"{side}_hand") or "").strip().upper()
            if not name or not source_id or not ioc:
                continue
            key = (_norm_name(name), ioc)
            item = grouped[key]
            item["canonical_source_ids"].add(source_id)
            item["canonical_iocs"].add(ioc)
            if hand:
                item["observed_hands"].add(hand)
            item["canonical_names"].add(name)
            item["rows"] += 1
            item["latest_row_date"] = max(item["latest_row_date"], tourney_date)
    return grouped


def expand_authority(
    *,
    runtime_dir: Path,
    history_csv: Path,
    static_cut_path: Path,
    authority: Mapping[str, Any],
    profile_fetcher: Callable[[str], Mapping[str, Any]],
    max_profiles: int = 12,
) -> tuple[dict[str, Any], dict[str, Any]]:
    aliases = dict(authority.get("country_code_aliases") or {})
    static_cut = _load(static_cut_path)
    candidates, conflicts = _candidate_identities(
        runtime_dir=runtime_dir,
        authority=authority,
        static_cut=static_cut,
    )
    history = _history_index(history_csv, aliases=aliases)
    records = [dict(row) for row in authority.get("records", []) or [] if isinstance(row, Mapping)]
    known_ids = {str(row.get("provider_player_id") or "") for row in records}
    added: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = list(conflicts)
    requests = 0

    for candidate in candidates:
        if len(added) >= max_profiles:
            blocked.append({
                "provider_player_id": candidate["provider_player_id"],
                "reason": "PROFILE_BUDGET_REACHED",
            })
            continue
        provider_id = candidate["provider_player_id"]
        if provider_id in known_ids:
            continue
        ioc = _canonical_ioc(candidate["provider_ioc_raw"], aliases)
        hist = history.get((_norm_name(candidate["display_name"]), ioc))
        if not hist:
            blocked.append({"provider_player_id": provider_id, "reason": "NO_PRE_CUT_CHALLENGER_HISTORY"})
            continue
        source_ids = sorted(hist["canonical_source_ids"])
        history_iocs = sorted(hist["canonical_iocs"])
        hands = sorted(hist["observed_hands"])
        names = sorted(hist["canonical_names"])
        if len(source_ids) != 1:
            blocked.append({"provider_player_id": provider_id, "reason": "PRE_CUT_SOURCE_ID_NOT_UNIQUE"})
            continue
        if history_iocs != [ioc]:
            blocked.append({"provider_player_id": provider_id, "reason": "PRE_CUT_IOC_NOT_UNIQUE"})
            continue
        if len(hands) != 1 or hands[0] not in {"R", "L"}:
            blocked.append({"provider_player_id": provider_id, "reason": "PRE_CUT_HAND_NOT_FIXED"})
            continue
        if len({_norm_name(x) for x in names}) != 1:
            blocked.append({"provider_player_id": provider_id, "reason": "PRE_CUT_NAME_NOT_UNIQUE"})
            continue

        profile = profile_fetcher(candidate["numeric_player_id"])
        requests += 1
        data = profile.get("data") if isinstance(profile.get("data"), Mapping) else profile
        if not isinstance(data, Mapping):
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_PAYLOAD_INVALID"})
            continue
        profile_id = str(data.get("id") or candidate["numeric_player_id"]).strip()
        profile_name = str(data.get("name") or "").strip()
        profile_ioc = _canonical_ioc(data.get("countryAcr"), aliases)
        info = data.get("information") if isinstance(data.get("information"), Mapping) else {}
        profile_hand = _hand_from_profile(info.get("plays") or info.get("hand"))
        dob = _dob_token(data.get("birthday"))
        if profile_id != candidate["numeric_player_id"]:
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_ID_MISMATCH"})
            continue
        if _norm_name(profile_name) != _norm_name(candidate["display_name"]):
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_NAME_MISMATCH"})
            continue
        if profile_ioc != ioc:
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_IOC_MISMATCH"})
            continue
        if profile_hand is not None and profile_hand != hands[0]:
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_HAND_CONFLICT"})
            continue
        if dob is None:
            blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_DOB_INVALID"})
            continue

        competitive_fields = [
            key for key in ("currentRank", "points", "progress", "careerMoney") if key in data
        ]
        record = {
            "provider_player_id": provider_id,
            "provider_display_name": candidate["display_name"],
            "provider_ioc_raw": candidate["provider_ioc_raw"],
            "provider_ioc_canonical": ioc,
            "ranking_cut": "2026-09-21",
            "provider_rank": candidate["provider_rank"],
            "provider_rank_points": candidate["provider_rank_points"],
            "pre_cut_history": {
                "canonical_source_ids": source_ids,
                "canonical_iocs": history_iocs,
                "observed_hands": hands,
                "rows": int(hist["rows"]),
                "latest_row_date": int(hist["latest_row_date"]),
            },
            "biographical_candidates": [{
                "master_id": "RAPIDAPI_PROFILE_" + candidate["numeric_player_id"],
                "name": profile_name,
                "hand": profile_hand or hands[0],
                "dob": dob,
                "ioc": profile_ioc,
                "height_cm": None,
                "wikidata_id": None,
                "provider_profile_sha256": _sha(profile),
            }],
            "biography_source": "RAPIDAPI_ULTRA_PROFILE_NUMERIC_ID_AUTOEXPAND",
            "profile_competitive_fields_discarded": competitive_fields,
        }
        records.append(record)
        known_ids.add(provider_id)
        added.append(record)

    output = dict(authority)
    output["schema"] = "MATRIX_COR0203_IDENTITY_AUTHORITY_AUTOEXPAND_V1"
    output["records"] = sorted(records, key=lambda row: str(row.get("provider_player_id") or ""))
    sources = list(output.get("sources") or [])
    marker = {
        "path": str(history_csv),
        "role": "strict_pre_cut_challenger_identity_history_autoexpand",
    }
    if marker not in sources:
        sources.append(marker)
    output["sources"] = sources
    output["post_cut_competitive_data_used"] = False
    output["outcomes_used"] = False
    output["odds_used"] = False
    output["automatic_wagering"] = False
    output["real_money"] = "BLOCKED"
    output["autoexpansion_audit"] = {
        "strict_before_period": 20260921,
        "candidate_provider_ids": [row["provider_player_id"] for row in candidates],
        "new_provider_player_ids": [row["provider_player_id"] for row in added],
        "new_records": len(added),
        "blocked": blocked,
        "profile_requests": requests,
        "join_by_name_only": False,
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
    }
    audit = {
        "schema": "MATRIX_COR0203_IDENTITY_AUTHORITY_EXPANSION_AUDIT_V1",
        "status": "PASS",
        "strict_before_period": 20260921,
        "candidate_count": len(candidates),
        "new_records": len(added),
        "new_provider_player_ids": [row["provider_player_id"] for row in added],
        "blocked": blocked,
        "profile_requests": requests,
        "authority_record_count": len(output["records"]),
        "post_cut_competitive_data_used": False,
        "outcomes_used": False,
        "odds_used": False,
        "metrics_opened": False,
        "real_money": "BLOCKED",
    }
    return output, audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--history-csv", default="evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv")
    parser.add_argument("--static-cut", default="evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json")
    parser.add_argument("--base-authority", default="evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R743.json")
    parser.add_argument("--out", default="evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json")
    parser.add_argument("--audit-out", default="evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_AUTHORITY_EXPANSION_LAST.json")
    parser.add_argument("--max-profiles", type=int, default=12)
    args = parser.parse_args()

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    out_path = Path(args.out)
    base_path = out_path if out_path.exists() else Path(args.base_authority)
    authority = _load(base_path)
    client = RapidApiTennisClient(key)

    def fetch_profile(numeric_id: str) -> Mapping[str, Any]:
        payload = client._get(f"/tennis/v2/atp/player/profile/{numeric_id}")
        return payload if isinstance(payload, Mapping) else {}

    output, audit = expand_authority(
        runtime_dir=Path(args.runtime_dir),
        history_csv=Path(args.history_csv),
        static_cut_path=Path(args.static_cut),
        authority=authority,
        profile_fetcher=fetch_profile,
        max_profiles=args.max_profiles,
    )
    audit["provider_network_calls"] = client.request_count
    _write(out_path, output)
    _write(Path(args.audit_out), audit)
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
