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


def _sealed_frozen_match(
    candidate: Mapping[str, Any],
    sealed_player_registry: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(sealed_player_registry, Mapping):
        return None, None
    matches = [
        (str(name), row)
        for name, row in sealed_player_registry.items()
        if isinstance(row, Mapping)
        and row.get("status") == "PASS"
        and _norm_name(name) == _norm_name(candidate.get("display_name"))
    ]
    if not matches:
        return None, None
    if len(matches) != 1:
        return None, "SEALED_FROZEN_IDENTITY_NONUNIQUE"
    canonical_name, row = matches[0]
    try:
        sealed_rank = int(row.get("rank"))
        sealed_points = int(row.get("rank_points"))
        candidate_rank = int(str(candidate.get("provider_rank") or "").strip())
        candidate_points = int(str(candidate.get("provider_rank_points") or "").strip())
        sealed_age = float(row.get("age"))
    except (TypeError, ValueError):
        return None, "SEALED_FROZEN_STATIC_INVALID"
    if (sealed_rank, sealed_points) != (candidate_rank, candidate_points):
        return None, "SEALED_FROZEN_RANK_POINTS_MISMATCH"
    sealed_hand = str(row.get("hand") or "").strip().upper()
    if sealed_hand not in {"R", "L"}:
        return None, "SEALED_FROZEN_HAND_INVALID"
    evidence_event_ids = sorted({
        str(x) for x in row.get("source_event_ids", []) or [] if str(x)
    })
    inherited_from = sorted({
        str(x) for x in row.get("inherited_from", []) or [] if str(x)
    })
    if not evidence_event_ids or not inherited_from:
        return None, "SEALED_FROZEN_PROVENANCE_MISSING"
    return {
        "canonical_name": canonical_name,
        "canonical_rank": sealed_rank,
        "canonical_rank_points": sealed_points,
        "canonical_hand": sealed_hand,
        "canonical_age": sealed_age,
        "canonical_source_id": evidence_event_ids[0],
        "evidence_event_ids": evidence_event_ids,
        "inherited_from": inherited_from,
        "physically_frozen": True,
    }, None


def _sealed_r706_provider_history_match(
    candidate: Mapping[str, Any],
    provider_history: Mapping[str, Any] | None,
    r706_readiness: Mapping[str, Any] | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not isinstance(provider_history, Mapping) or not isinstance(r706_readiness, Mapping):
        return None, None
    if str(provider_history.get("cutoff_exclusive_utc") or "") != "2026-09-21T00:00:00+00:00":
        return None, "PROVIDER_HISTORY_CUT_MISMATCH"
    if provider_history.get("metrics_opened") is not False:
        return None, "PROVIDER_HISTORY_METRICS_FLAG_INVALID"
    if int(provider_history.get("outcomes_used_for_metrics") or 0) != 0:
        return None, "PROVIDER_HISTORY_OUTCOMES_FLAG_INVALID"
    if r706_readiness.get("state_mutated") is not False:
        return None, "R706_STATE_MUTATION_FLAG_INVALID"
    if r706_readiness.get("metrics_opened") is not False:
        return None, "R706_METRICS_FLAG_INVALID"
    if int(r706_readiness.get("outcomes_read") or 0) != 0:
        return None, "R706_OUTCOMES_FLAG_INVALID"

    provider_id = str(candidate.get("provider_player_id") or "")
    target_rows = [
        row
        for row in provider_history.get("targets", []) or []
        if isinstance(row, Mapping)
        and str(row.get("provider_player_id") or "") == provider_id
    ]
    if not target_rows:
        return None, None
    if len(target_rows) != 1:
        return None, "PROVIDER_HISTORY_TARGET_NONUNIQUE"
    provider_row = target_rows[0]
    try:
        eligible = int(provider_row.get("eligible_pre_cut_matches") or 0)
    except (TypeError, ValueError):
        eligible = 0
    if eligible <= 0:
        return None, "PROVIDER_PRECUT_HISTORY_EMPTY"
    display_name = str(candidate.get("display_name") or "").strip()
    observed_names = [
        str(x).strip()
        for x in provider_row.get("observed_names", []) or []
        if str(x).strip()
    ]
    if not observed_names or any(
        _norm_name(x) != _norm_name(display_name)
        for x in observed_names
    ):
        return None, "PROVIDER_HISTORY_NAME_MISMATCH"

    state_rows = [
        row
        for row in r706_readiness.get("targets", []) or []
        if isinstance(row, Mapping)
        and _norm_name(row.get("name")) == _norm_name(display_name)
    ]
    if not state_rows:
        return None, "R706_HISTORY_TARGET_MISSING"
    if len(state_rows) != 1:
        return None, "R706_HISTORY_TARGET_NONUNIQUE"
    state_row = state_rows[0]
    if state_row.get("fully_history_ready") is not True:
        return None, "R706_MODEL_HISTORY_NOT_READY"
    required = state_row.get("required_components")
    if not isinstance(required, Mapping) or not required or not all(
        value is True for value in required.values()
    ):
        return None, "R706_MODEL_HISTORY_COMPONENT_MISSING"
    state_sha = str(r706_readiness.get("state_sha256") or "").strip()
    if len(state_sha) != 64:
        return None, "R706_STATE_SHA_INVALID"

    return {
        "name": str(state_row.get("name") or display_name),
        "fully_history_ready": True,
        "required_components": dict(required),
        "counts": dict(state_row.get("counts") or {}),
        "ratings": dict(state_row.get("ratings") or {}),
        "state_sha256": state_sha,
        "provider_player_id": provider_id,
        "eligible_pre_cut_matches": eligible,
        "observed_names": observed_names,
        "cutoff_exclusive_utc": "2026-09-21T00:00:00+00:00",
    }, None


def _biography_supplement_hand(
    candidate: Mapping[str, Any],
    supplement: Mapping[str, Any] | None,
) -> str | None:
    if not isinstance(supplement, Mapping):
        return None
    if supplement.get("competitive_fields_used") is not False:
        return None
    if supplement.get("outcomes_used") is not False:
        return None
    if supplement.get("odds_used") is not False:
        return None
    provider_id = str(candidate.get("provider_player_id") or "")
    display_name = str(candidate.get("display_name") or "").strip()
    rows = [
        row
        for row in supplement.get("records", []) or []
        if isinstance(row, Mapping)
        and str(row.get("provider_player_id") or "") == provider_id
        and _norm_name(row.get("canonical_name")) == _norm_name(display_name)
    ]
    if len(rows) != 1:
        return None
    hand = str(rows[0].get("hand") or "").strip().upper()
    return hand if hand in {"R", "L"} else None


def expand_authority(
    *,
    runtime_dir: Path,
    history_csv: Path,
    static_cut_path: Path,
    authority: Mapping[str, Any],
    profile_fetcher: Callable[[str], Mapping[str, Any]],
    max_profiles: int = 12,
    sealed_player_registry: Mapping[str, Mapping[str, Any]] | None = None,
    provider_history: Mapping[str, Any] | None = None,
    r706_readiness: Mapping[str, Any] | None = None,
    biography_supplement: Mapping[str, Any] | None = None,
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
            sealed, sealed_reason = _sealed_frozen_match(
                candidate,
                sealed_player_registry,
            )
            if sealed_reason is not None:
                blocked.append({
                    "provider_player_id": provider_id,
                    "reason": sealed_reason,
                })
                continue
            if sealed is None:
                r706_evidence, r706_reason = _sealed_r706_provider_history_match(
                    candidate,
                    provider_history,
                    r706_readiness,
                )
                if r706_reason is not None:
                    blocked.append({
                        "provider_player_id": provider_id,
                        "reason": r706_reason,
                    })
                    continue
                if r706_evidence is None:
                    blocked.append({
                        "provider_player_id": provider_id,
                        "reason": "NO_PRE_CUT_CHALLENGER_HISTORY",
                    })
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
                hand_source = "RAPIDAPI_PROFILE"
                if profile_hand not in {"R", "L"}:
                    profile_hand = _biography_supplement_hand(
                        candidate,
                        biography_supplement,
                    )
                    if profile_hand in {"R", "L"}:
                        hand_source = "BIOGRAPHY_SUPPLEMENT"
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
                if profile_hand not in {"R", "L"}:
                    blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_HAND_INVALID"})
                    continue
                if dob is None:
                    blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_DOB_INVALID"})
                    continue

                competitive_fields = [
                    key for key in ("currentRank", "points", "progress", "careerMoney") if key in data
                ]
                canonical_source_id = (
                    "R706_STATE_RAPIDAPI_PLAYER_" + candidate["numeric_player_id"]
                )
                record = {
                    "provider_player_id": provider_id,
                    "provider_display_name": candidate["display_name"],
                    "canonical_name": r706_evidence["name"],
                    "canonical_source_id": canonical_source_id,
                    "provider_ioc_raw": candidate["provider_ioc_raw"],
                    "provider_ioc_canonical": ioc,
                    "ranking_cut": "2026-09-21",
                    "provider_rank": candidate["provider_rank"],
                    "provider_rank_points": candidate["provider_rank_points"],
                    "authority_basis": (
                        "SEALED_R706_STATE_PLUS_PRECUT_PROVIDER_HISTORY_AND_PROFILE"
                    ),
                    "sealed_r706_history": {
                        "name": r706_evidence["name"],
                        "fully_history_ready": True,
                        "required_components": r706_evidence["required_components"],
                        "counts": r706_evidence["counts"],
                        "ratings": r706_evidence["ratings"],
                        "state_sha256": r706_evidence["state_sha256"],
                    },
                    "pre_cut_provider_history": {
                        "provider_player_id": provider_id,
                        "eligible_pre_cut_matches": r706_evidence["eligible_pre_cut_matches"],
                        "observed_names": r706_evidence["observed_names"],
                        "cutoff_exclusive_utc": r706_evidence["cutoff_exclusive_utc"],
                    },
                    "biographical_candidates": [{
                        "master_id": "RAPIDAPI_PROFILE_" + candidate["numeric_player_id"],
                        "name": profile_name,
                        "hand": profile_hand,
                        "dob": dob,
                        "ioc": profile_ioc,
                        "height_cm": None,
                        "wikidata_id": None,
                        "provider_profile_sha256": _sha(profile),
                    }],
                    "biography_source": "RAPIDAPI_ULTRA_PROFILE_NUMERIC_ID_AUTOEXPAND",
                    "hand_source": hand_source,
                    "profile_competitive_fields_discarded": competitive_fields,
                }
                records.append(record)
                known_ids.add(provider_id)
                added.append(record)
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
            if profile_hand is not None and profile_hand != sealed["canonical_hand"]:
                blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_HAND_CONFLICT"})
                continue
            if dob is None:
                blocked.append({"provider_player_id": provider_id, "reason": "PROFILE_DOB_INVALID"})
                continue
            parsed_dob = date(int(dob[:4]), int(dob[4:6]), int(dob[6:8]))
            profile_age = (CUT_DATE - parsed_dob).days / 365.25
            if abs(profile_age - float(sealed["canonical_age"])) > 0.02:
                blocked.append({
                    "provider_player_id": provider_id,
                    "reason": "PROFILE_SEALED_AGE_CONFLICT",
                })
                continue

            competitive_fields = [
                key for key in ("currentRank", "points", "progress", "careerMoney") if key in data
            ]
            record = {
                "provider_player_id": provider_id,
                "provider_display_name": candidate["display_name"],
                "canonical_name": sealed["canonical_name"],
                "provider_ioc_raw": candidate["provider_ioc_raw"],
                "provider_ioc_canonical": ioc,
                "ranking_cut": "2026-09-21",
                "provider_rank": candidate["provider_rank"],
                "provider_rank_points": candidate["provider_rank_points"],
                "authority_basis": "SEALED_FROZEN_STATIC4_PLUS_PROFILE",
                "sealed_frozen_identity": sealed,
                "biographical_candidates": [{
                    "master_id": "RAPIDAPI_PROFILE_" + candidate["numeric_player_id"],
                    "name": profile_name,
                    "hand": profile_hand or sealed["canonical_hand"],
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



def merge_certified_aliases(
    authority: Mapping[str, Any],
    aliases: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(aliases, Mapping):
        return dict(authority), []
    if int(aliases.get("strict_before_period") or 0) != 20260921:
        raise ValueError("CERTIFIED_ALIAS_CUT_MISMATCH")
    if aliases.get("post_cut_competitive_data_used") is not False:
        raise ValueError("CERTIFIED_ALIAS_POSTCUT_FLAG_INVALID")
    if aliases.get("outcomes_used") is not False:
        raise ValueError("CERTIFIED_ALIAS_OUTCOME_FLAG_INVALID")
    if aliases.get("odds_used") is not False:
        raise ValueError("CERTIFIED_ALIAS_ODDS_FLAG_INVALID")
    if aliases.get("metrics_opened") is not False:
        raise ValueError("CERTIFIED_ALIAS_METRICS_FLAG_INVALID")
    if aliases.get("real_money") != "BLOCKED":
        raise ValueError("CERTIFIED_ALIAS_REAL_MONEY_FLAG_INVALID")

    out=dict(authority)
    records=[
        dict(row)
        for row in out.get("records", []) or []
        if isinstance(row, Mapping)
    ]
    by_id={
        str(row.get("provider_player_id") or ""): row
        for row in records
        if str(row.get("provider_player_id") or "")
    }
    added=[]
    for raw in aliases.get("records", []) or []:
        if not isinstance(raw, Mapping):
            raise ValueError("CERTIFIED_ALIAS_RECORD_INVALID")
        row=dict(raw)
        provider_id=str(row.get("provider_player_id") or "")
        canonical_name=str(row.get("canonical_name") or "")
        history=row.get("pre_cut_history")
        bios=row.get("biographical_candidates")
        if not provider_id or not canonical_name:
            raise ValueError("CERTIFIED_ALIAS_IDENTITY_MISSING")
        if str(row.get("ranking_cut") or "").replace("-", "") != "20260921":
            raise ValueError("CERTIFIED_ALIAS_RANKING_CUT_INVALID:" + provider_id)
        if not isinstance(history, Mapping):
            raise ValueError("CERTIFIED_ALIAS_HISTORY_MISSING:" + provider_id)
        source_ids=[str(x) for x in history.get("canonical_source_ids", []) or [] if str(x)]
        if len(set(source_ids)) != 1:
            raise ValueError("CERTIFIED_ALIAS_SOURCE_ID_NOT_UNIQUE:" + provider_id)
        if not isinstance(bios, list) or len(bios) != 1 or not isinstance(bios[0], Mapping):
            raise ValueError("CERTIFIED_ALIAS_BIOGRAPHY_NOT_UNIQUE:" + provider_id)
        existing=by_id.get(provider_id)
        if existing is not None:
            if (
                str(existing.get("canonical_name") or existing.get("provider_display_name") or "")
                != canonical_name
                or str((existing.get("pre_cut_history") or {}).get("canonical_source_ids", [""])[0])
                != source_ids[0]
            ):
                raise ValueError("CERTIFIED_ALIAS_PROVIDER_ID_COLLISION:" + provider_id)
            continue
        records.append(row)
        by_id[provider_id]=row
        added.append(provider_id)
    out["records"]=records
    out["certified_alias_source"]=str(
        aliases.get("schema") or "MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1"
    )
    return out, added


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-dir", default="evidence/cor0203/runtime")
    parser.add_argument("--history-csv", default="evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv")
    parser.add_argument("--holdout-dir", default="evidence/cor0203/holdout")
    parser.add_argument("--static-cut", default="evidence/cor0203/runtime/MATRIX_COR0203_STATIC_CUT_20260921.json")
    parser.add_argument("--base-authority", default="evidence/cor0203/identity/MATRIX_COR0203_ATP_BIOGRAPHICAL_SUBSET_R743.json")
    parser.add_argument("--out", default="evidence/cor0203/identity/MATRIX_COR0203_IDENTITY_AUTHORITY_LAST.json")
    parser.add_argument("--audit-out", default="evidence/cor0203/runtime/MATRIX_COR0203_IDENTITY_AUTHORITY_EXPANSION_LAST.json")
    parser.add_argument("--max-profiles", type=int, default=12)
    parser.add_argument(
        "--provider-history",
        default=(
            "evidence/cor0203/rapidapi_stats_rich/"
            "MATRIX_COR0203_RAPIDAPI_PRECUT_STATS_RICH_PROBE_LAST.json"
        ),
    )
    parser.add_argument(
        "--r706-readiness",
        default=(
            "evidence/cor0203/runtime/"
            "MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_LAST.json"
        ),
    )
    parser.add_argument(
        "--biography-supplement",
        default=(
            "evidence/cor0203/identity/"
            "MATRIX_COR0203_BIOGRAPHY_SUPPLEMENT_20261003.json"
        ),
    )
    parser.add_argument(
        "--certified-aliases",
        default=(
            "evidence/cor0203/identity/"
            "MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_20261003.json"
        ),
    )
    args = parser.parse_args()

    key = os.environ.get("RAPIDAPI_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    out_path = Path(args.out)
    base_path = out_path if out_path.exists() else Path(args.base_authority)
    authority = _load(base_path)
    certified_alias_path = Path(args.certified_aliases)
    certified_aliases = (
        _load(certified_alias_path)
        if certified_alias_path.exists()
        else None
    )
    authority, certified_aliases_added = merge_certified_aliases(
        authority,
        certified_aliases,
    )
    client = RapidApiTennisClient(key)

    def fetch_profile(numeric_id: str) -> Mapping[str, Any]:
        payload = client._get(f"/tennis/v2/atp/player/profile/{numeric_id}")
        return payload if isinstance(payload, Mapping) else {}

    from tools.cor0203_stage_from_registry import build_sealed_player_registry

    sealed_player_registry = build_sealed_player_registry(
        runtime_dir=Path(args.runtime_dir),
        holdout_dir=Path(args.holdout_dir),
    )
    provider_history_path = Path(args.provider_history)
    r706_readiness_path = Path(args.r706_readiness)
    provider_history = (
        _load(provider_history_path)
        if provider_history_path.exists()
        else None
    )
    r706_readiness = (
        _load(r706_readiness_path)
        if r706_readiness_path.exists()
        else None
    )
    biography_supplement_path = Path(args.biography_supplement)
    biography_supplement = (
        _load(biography_supplement_path)
        if biography_supplement_path.exists()
        else None
    )
    output, audit = expand_authority(
        runtime_dir=Path(args.runtime_dir),
        history_csv=Path(args.history_csv),
        static_cut_path=Path(args.static_cut),
        authority=authority,
        profile_fetcher=fetch_profile,
        max_profiles=args.max_profiles,
        sealed_player_registry=sealed_player_registry,
        provider_history=provider_history,
        r706_readiness=r706_readiness,
        biography_supplement=biography_supplement,
    )
    audit["sealed_frozen_registry_players"] = len(sealed_player_registry)
    audit["sealed_frozen_promotions"] = [
        row["provider_player_id"]
        for row in output.get("records", [])
        if row.get("authority_basis") == "SEALED_FROZEN_STATIC4_PLUS_PROFILE"
    ]
    audit["sealed_r706_history_promotions"] = [
        row["provider_player_id"]
        for row in output.get("records", [])
        if row.get("authority_basis")
        == "SEALED_R706_STATE_PLUS_PRECUT_PROVIDER_HISTORY_AND_PROFILE"
    ]
    audit["certified_aliases_loaded"] = (
        len(certified_aliases.get("records", []))
        if isinstance(certified_aliases, Mapping)
        else 0
    )
    audit["certified_aliases_added_to_authority"] = certified_aliases_added
    audit["provider_network_calls"] = client.request_count
    _write(out_path, output)
    _write(Path(args.audit_out), audit)
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
