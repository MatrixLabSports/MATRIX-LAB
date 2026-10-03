from __future__ import annotations

from datetime import date
from typing import Any, Mapping
import unicodedata


CUT_DATE = date(2026, 9, 21)
CUT_TOKEN = "20260921"
COUNTRY_ALIASES = {
    "POR": "PRT",
}


def _norm_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    return "".join(ch for ch in text if ch.isalnum())


def _canonical_ioc(value: object) -> str:
    token = str(value or "").strip().upper()
    return COUNTRY_ALIASES.get(token, token)


def _parse_dob(value: object) -> date | None:
    token = str(value or "").strip()
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        return date(int(token[:4]), int(token[4:6]), int(token[6:8]))
    except ValueError:
        return None


def _age_at_cut(dob: date) -> float:
    return round((CUT_DATE - dob).days / 365.25, 3)


def build_provider_authority_index(
    authority: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(authority, Mapping):
        return {}
    if authority.get("post_cut_competitive_data_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_POST_CUT_FLAG_INVALID")
    if authority.get("outcomes_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_OUTCOME_FLAG_INVALID")
    if authority.get("odds_used") is not False:
        raise ValueError("IDENTITY_AUTHORITY_ODDS_FLAG_INVALID")

    schema = str(authority.get("schema") or "")
    authority_name = schema[:-3] if schema.endswith("_V1") else schema
    index: dict[str, Mapping[str, Any]] = {}
    for row in authority.get("records", []) or []:
        if not isinstance(row, Mapping):
            continue
        provider_id = str(row.get("provider_player_id") or "")
        if not provider_id:
            continue
        if provider_id in index:
            raise ValueError("IDENTITY_AUTHORITY_PROVIDER_ID_DUPLICATE:" + provider_id)
        indexed_row = dict(row)
        indexed_row["_identity_authority"] = authority_name
        index[provider_id] = indexed_row
    return index


def resolve_authority_mapping(
    *,
    identity: Mapping[str, Any],
    provider: str,
    provider_id: str,
    ranking: Mapping[str, Any],
    rank: int,
    points: int,
    authority_index: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    row = authority_index.get(provider_id)
    if not isinstance(row, Mapping):
        return None, "IDENTITY_AUTHORITY_MISSING:" + provider_id

    snapshot = str(ranking.get("snapshot_date") or "").replace("-", "")
    if snapshot != CUT_TOKEN or str(row.get("ranking_cut") or "").replace("-", "") != CUT_TOKEN:
        return None, "IDENTITY_AUTHORITY_RANKING_CUT_MISMATCH:" + provider_id

    display_name = str(identity.get("display_name") or "").strip()
    provider_name = str(ranking.get("player") or display_name).strip()
    authority_name = str(row.get("provider_display_name") or "").strip()
    canonical_name = str(row.get("canonical_name") or authority_name).strip()
    if (
        not authority_name
        or _norm_name(authority_name) not in {_norm_name(display_name), _norm_name(provider_name)}
    ):
        return None, "IDENTITY_AUTHORITY_NAME_MISMATCH:" + provider_id

    provider_ioc = _canonical_ioc(ranking.get("country"))
    authority_ioc = _canonical_ioc(row.get("provider_ioc_canonical"))
    if not provider_ioc or provider_ioc != authority_ioc:
        return None, "IDENTITY_AUTHORITY_IOC_MISMATCH:" + provider_id

    if str(row.get("authority_basis") or "") == "SEALED_FROZEN_STATIC4_PLUS_PROFILE":
        sealed = row.get("sealed_frozen_identity")
        if not isinstance(sealed, Mapping):
            return None, "IDENTITY_AUTHORITY_SEALED_FROZEN_MISSING:" + provider_id
        if sealed.get("physically_frozen") is not True:
            return None, "IDENTITY_AUTHORITY_SEALED_FROZEN_NOT_PROVEN:" + provider_id
        sealed_name = str(sealed.get("canonical_name") or "").strip()
        if not sealed_name or _norm_name(sealed_name) != _norm_name(canonical_name):
            return None, "IDENTITY_AUTHORITY_SEALED_NAME_MISMATCH:" + provider_id
        try:
            sealed_rank = int(sealed.get("canonical_rank"))
            sealed_points = int(sealed.get("canonical_rank_points"))
            sealed_age = float(sealed.get("canonical_age"))
        except (TypeError, ValueError):
            return None, "IDENTITY_AUTHORITY_SEALED_STATIC_INVALID:" + provider_id
        if (sealed_rank, sealed_points) != (rank, points):
            return None, "IDENTITY_AUTHORITY_SEALED_RANK_POINTS_MISMATCH:" + provider_id
        sealed_hand = str(sealed.get("canonical_hand") or "").strip().upper()
        if sealed_hand not in {"R", "L"}:
            return None, "IDENTITY_AUTHORITY_SEALED_HAND_INVALID:" + provider_id
        evidence_event_ids = [
            str(x) for x in sealed.get("evidence_event_ids", []) or [] if str(x)
        ]
        inherited_from = [
            str(x) for x in sealed.get("inherited_from", []) or [] if str(x)
        ]
        canonical_source_id = str(sealed.get("canonical_source_id") or "").strip()
        if not evidence_event_ids or not inherited_from or not canonical_source_id:
            return None, "IDENTITY_AUTHORITY_SEALED_PROVENANCE_MISSING:" + provider_id

        bios = row.get("biographical_candidates")
        if not isinstance(bios, list) or len(bios) != 1 or not isinstance(bios[0], Mapping):
            return None, "IDENTITY_AUTHORITY_BIOGRAPHY_NOT_UNIQUE:" + provider_id
        bio = bios[0]
        if _norm_name(bio.get("name")) != _norm_name(authority_name):
            return None, "IDENTITY_AUTHORITY_BIOGRAPHY_NAME_MISMATCH:" + provider_id
        if _canonical_ioc(bio.get("ioc")) != provider_ioc:
            return None, "IDENTITY_AUTHORITY_BIOGRAPHY_IOC_MISMATCH:" + provider_id
        bio_hand = str(bio.get("hand") or "").strip().upper()
        if bio_hand in {"R", "L"} and bio_hand != sealed_hand:
            return None, "IDENTITY_AUTHORITY_BIOGRAPHY_HAND_CONFLICT:" + provider_id
        dob = _parse_dob(bio.get("dob"))
        if dob is None or dob >= CUT_DATE:
            return None, "IDENTITY_AUTHORITY_DOB_INVALID:" + provider_id
        canonical_age = _age_at_cut(dob)
        if abs(canonical_age - sealed_age) > 0.02:
            return None, "IDENTITY_AUTHORITY_SEALED_AGE_CONFLICT:" + provider_id

        return {
            "provider": provider,
            "provider_player_id": provider_id,
            "provider_display_name": display_name,
            "provider_ranking_name": provider_name,
            "provider_rank": rank,
            "provider_rank_points": points,
            "canonical_source_id": canonical_source_id,
            "canonical_name": canonical_name,
            "canonical_rank": sealed_rank,
            "canonical_rank_points": sealed_points,
            "canonical_hand": sealed_hand,
            "canonical_age": canonical_age,
            "canonical_ioc": provider_ioc,
            "canonical_dob": dob.isoformat(),
            "ranking_cut": CUT_TOKEN,
            "match_basis": (
                "EXACT_PROVIDER_ID_PLUS_NAME_IOC_RANK_POINTS_"
                "PLUS_SEALED_FROZEN_STATIC4_AND_PROFILE_DOB"
            ),
            "identity_authority": str(row.get("_identity_authority") or ""),
            "status": "PASS",
        }, None

    history = row.get("pre_cut_history")
    if not isinstance(history, Mapping):
        return None, "IDENTITY_AUTHORITY_HISTORY_MISSING:" + provider_id
    source_ids = [str(x) for x in history.get("canonical_source_ids", []) or [] if str(x)]
    history_iocs = [_canonical_ioc(x) for x in history.get("canonical_iocs", []) or [] if str(x)]
    hands = [str(x).strip().upper() for x in history.get("observed_hands", []) or [] if str(x).strip()]
    if len(set(source_ids)) != 1:
        return None, "IDENTITY_AUTHORITY_SOURCE_ID_NOT_UNIQUE:" + provider_id

    if canonical_name != authority_name:
        canonical_source = row.get("canonical_name_source")
        if not isinstance(canonical_source, Mapping):
            return None, "IDENTITY_AUTHORITY_CANONICAL_NAME_SOURCE_MISSING:" + provider_id
        if str(canonical_source.get("canonical_source_id") or "") != source_ids[0]:
            return None, "IDENTITY_AUTHORITY_CANONICAL_NAME_SOURCE_ID_MISMATCH:" + provider_id
        if int(canonical_source.get("strict_before_period") or 0) != 20260921:
            return None, "IDENTITY_AUTHORITY_CANONICAL_NAME_CUT_MISMATCH:" + provider_id
        if int(canonical_source.get("rows") or 0) <= 0:
            return None, "IDENTITY_AUTHORITY_CANONICAL_NAME_ROWS_MISSING:" + provider_id
    if len(set(history_iocs)) != 1 or history_iocs[0] != provider_ioc:
        return None, "IDENTITY_AUTHORITY_HISTORY_IOC_MISMATCH:" + provider_id
    if len(set(hands)) != 1 or hands[0] not in {"R", "L"}:
        return None, "IDENTITY_AUTHORITY_HAND_NOT_FIXED:" + provider_id

    bios = row.get("biographical_candidates")
    if not isinstance(bios, list) or len(bios) != 1 or not isinstance(bios[0], Mapping):
        return None, "IDENTITY_AUTHORITY_BIOGRAPHY_NOT_UNIQUE:" + provider_id
    bio = bios[0]
    if _norm_name(bio.get("name")) != _norm_name(authority_name):
        return None, "IDENTITY_AUTHORITY_BIOGRAPHY_NAME_MISMATCH:" + provider_id
    if _canonical_ioc(bio.get("ioc")) != provider_ioc:
        return None, "IDENTITY_AUTHORITY_BIOGRAPHY_IOC_MISMATCH:" + provider_id
    bio_hand = str(bio.get("hand") or "").strip().upper()
    if bio_hand in {"R", "L"} and bio_hand != hands[0]:
        return None, "IDENTITY_AUTHORITY_BIOGRAPHY_HAND_CONFLICT:" + provider_id
    dob = _parse_dob(bio.get("dob"))
    if dob is None or dob >= CUT_DATE:
        return None, "IDENTITY_AUTHORITY_DOB_INVALID:" + provider_id

    return {
        "provider": provider,
        "provider_player_id": provider_id,
        "provider_display_name": display_name,
        "provider_ranking_name": provider_name,
        "provider_rank": rank,
        "provider_rank_points": points,
        "canonical_source_id": source_ids[0],
        "canonical_name": canonical_name,
        "canonical_rank": rank,
        "canonical_rank_points": points,
        "canonical_hand": hands[0],
        "canonical_age": _age_at_cut(dob),
        "canonical_ioc": provider_ioc,
        "canonical_dob": dob.isoformat(),
        "ranking_cut": CUT_TOKEN,
        "match_basis": (
            "EXACT_PROVIDER_ID_PLUS_NAME_IOC_UNIQUE_PRECUT_SOURCE_ID_"
            "PLUS_FIXED_BIOGRAPHY_DOB_AND_DATED_PROVIDER_RANKING"
        ),
        "identity_authority": str(row.get("_identity_authority") or ""),
        "status": "PASS",
    }, None
