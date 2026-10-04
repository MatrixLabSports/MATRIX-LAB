from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient

CUT_TOKEN = 20260921
CUT_DATE = date(2026, 9, 21)
PROVIDER_NUMERIC_ID = "76009"
PROVIDER_ID = "rapidapi-tennis:player:76009"
PROVIDER_DISPLAY_NAME = "Abedallah Shelbayh"
CANONICAL_NAME = "Abdullah Shelbayh"
CANONICAL_SOURCE_ID = "S0NV"
CANONICAL_IOC = "JOR"
CANONICAL_HAND = "L"


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _dob_token(value: object) -> str | None:
    token = str(value or "").strip()[:10].replace("-", "")
    if len(token) != 8 or not token.isdigit():
        return None
    try:
        parsed = date(int(token[:4]), int(token[4:6]), int(token[6:8]))
    except ValueError:
        return None
    return token if parsed < CUT_DATE else None


def _profile_hand(value: object) -> str | None:
    token = str(value or "").strip().casefold()
    if token.startswith("left"):
        return "L"
    if token.startswith("right"):
        return "R"
    return None


def _date_token(value: object) -> date:
    token = str(value or "").strip()
    if not re.fullmatch(r"\d{8}", token):
        raise ValueError("HISTORY_DATE_INVALID:" + token)
    return date(int(token[:4]), int(token[4:6]), int(token[6:8]))


def _finite(value: object) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _history_proof(path: Path, dob: date) -> dict[str, Any]:
    rows = list(csv.DictReader(path.read_text(encoding="utf-8-sig").splitlines()))
    matched: list[dict[str, Any]] = []
    for row in rows:
        try:
            period = int(float(str(row.get("tourney_date") or "0")))
        except ValueError:
            continue
        if period >= CUT_TOKEN or str(row.get("tourney_level") or "").strip() != "C":
            continue
        for side in ("winner", "loser"):
            if str(row.get(f"{side}_id") or "").strip() != CANONICAL_SOURCE_ID:
                continue
            matched.append({"row": row, "side": side})
    if not matched:
        raise ValueError("SHELBAYH_CANONICAL_PRECUT_HISTORY_MISSING")

    names = {_norm(item["row"].get(f'{item["side"]}_name')) for item in matched}
    iocs = {str(item["row"].get(f'{item["side"]}_ioc') or "").strip().upper() for item in matched}
    hands = {str(item["row"].get(f'{item["side"]}_hand') or "").strip().upper() for item in matched}
    if names != {_norm(CANONICAL_NAME)}:
        raise ValueError("SHELBAYH_CANONICAL_NAME_NOT_UNIQUE")
    if iocs != {CANONICAL_IOC}:
        raise ValueError("SHELBAYH_CANONICAL_IOC_NOT_UNIQUE")
    if hands != {CANONICAL_HAND}:
        raise ValueError("SHELBAYH_CANONICAL_HAND_NOT_UNIQUE")

    age_errors = []
    stats_rich_rows = 0
    dates = []
    for item in matched:
        row=item["row"]
        side=item["side"]
        played=_date_token(row["tourney_date"])
        dates.append(int(row["tourney_date"]))
        observed_age=float(row[f"{side}_age"])
        expected_age=(played-dob).days/365.25
        age_errors.append(abs(observed_age-expected_age))
        required = (
            "w_svpt","w_1stWon","w_2ndWon",
            "l_svpt","l_1stWon","l_2ndWon",
        )
        if all(_finite(row.get(field)) and float(row[field]) > 0 for field in required):
            stats_rich_rows += 1

    if max(age_errors) > 0.03:
        raise ValueError("SHELBAYH_DOB_HISTORY_AGE_CONFLICT")
    if stats_rich_rows <= 0:
        raise ValueError("SHELBAYH_STATS_RICH_HISTORY_MISSING")

    return {
        "canonical_source_ids":[CANONICAL_SOURCE_ID],
        "canonical_iocs":[CANONICAL_IOC],
        "observed_hands":[CANONICAL_HAND],
        "rows":len(matched),
        "stats_rich_rows":stats_rich_rows,
        "latest_row_date":max(dates),
        "earliest_row_date":min(dates),
        "max_age_error_years":max(age_errors),
    }


def _provider_ranking_proof(runtime_dir: Path) -> dict[str, Any]:
    rows=[]
    for path in sorted(runtime_dir.glob("MATRIX_COR0203_PREFEATURE_REGISTRY_R*.json")):
        payload=_load(path)
        for event in payload.get("events", []) or []:
            for identity in event.get("player_identities", []) or []:
                if str(identity.get("provider_player_id") or "") != PROVIDER_ID:
                    continue
                ranking=identity.get("provider_ranking")
                if not isinstance(ranking, Mapping):
                    continue
                rows.append({
                    "display_name":str(identity.get("display_name") or "").strip(),
                    "country":str(ranking.get("country") or "").strip().upper(),
                    "place":str(ranking.get("place") or "").strip(),
                    "points":str(ranking.get("points") or "").strip(),
                    "player":str(ranking.get("player") or "").strip(),
                    "snapshot_date":str(ranking.get("snapshot_date") or "").strip(),
                    "source_prefeature":path.name,
                    "source_event_id":str(event.get("event_id") or ""),
                })
    if not rows:
        raise ValueError("SHELBAYH_PROVIDER_RANKING_EVIDENCE_MISSING")
    signatures={
        (
            _norm(row["display_name"]),
            _norm(row["player"]),
            row["country"],
            row["place"],
            row["points"],
            row["snapshot_date"],
        )
        for row in rows
    }
    if len(signatures) != 1:
        raise ValueError("SHELBAYH_PROVIDER_RANKING_EVIDENCE_CONFLICT")
    row=rows[-1]
    if _norm(row["display_name"]) != _norm(PROVIDER_DISPLAY_NAME):
        raise ValueError("SHELBAYH_PROVIDER_DISPLAY_NAME_MISMATCH")
    if row["country"] != CANONICAL_IOC:
        raise ValueError("SHELBAYH_PROVIDER_COUNTRY_MISMATCH")
    if row["snapshot_date"] != "2026-09-21":
        raise ValueError("SHELBAYH_PROVIDER_RANKING_CUT_MISMATCH")
    if not row["place"].isdigit() or not row["points"].isdigit():
        raise ValueError("SHELBAYH_PROVIDER_RANK_POINTS_INVALID")
    return {
        "provider_rank":row["place"],
        "provider_rank_points":row["points"],
        "provider_ioc":row["country"],
        "ranking_cut":"2026-09-21",
        "evidence_rows":len(rows),
        "source_prefeatures":sorted({x["source_prefeature"] for x in rows}),
        "source_event_ids":sorted({x["source_event_id"] for x in rows}),
    }


def _r706_proof(path: Path) -> dict[str, Any]:
    payload=_load(path)
    if payload.get("state_mutated") is not False:
        raise ValueError("R706_STATE_MUTATION_FLAG_INVALID")
    if payload.get("metrics_opened") is not False or int(payload.get("outcomes_read") or 0) != 0:
        raise ValueError("R706_METRICS_OR_OUTCOME_FLAG_INVALID")
    rows=[
        row for row in payload.get("targets", []) or []
        if _norm(row.get("name")) == _norm(CANONICAL_NAME)
    ]
    if len(rows) != 1:
        raise ValueError("R706_CANONICAL_SHELBAYH_NONUNIQUE")
    row=rows[0]
    required=row.get("required_components")
    if row.get("fully_history_ready") is not True:
        raise ValueError("R706_CANONICAL_SHELBAYH_NOT_READY")
    if not isinstance(required, Mapping) or not required or not all(v is True for v in required.values()):
        raise ValueError("R706_CANONICAL_SHELBAYH_COMPONENT_MISSING")
    state_sha=str(payload.get("state_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", state_sha):
        raise ValueError("R706_STATE_SHA_INVALID")
    return {
        "name":CANONICAL_NAME,
        "fully_history_ready":True,
        "required_components":dict(required),
        "counts":dict(row.get("counts") or {}),
        "ratings":dict(row.get("ratings") or {}),
        "state_sha256":state_sha,
    }


def build_certificate(
    *,
    profile: Mapping[str, Any],
    history_csv: Path,
    runtime_dir: Path,
    r706_path: Path,
) -> dict[str, Any]:
    data=profile.get("data") if isinstance(profile.get("data"), Mapping) else profile
    if not isinstance(data, Mapping):
        raise ValueError("SHELBAYH_PROFILE_PAYLOAD_INVALID")
    profile_id=str(data.get("id") or "").strip()
    profile_name=str(data.get("name") or "").strip()
    profile_ioc=str(data.get("countryAcr") or "").strip().upper()
    info=data.get("information") if isinstance(data.get("information"), Mapping) else {}
    hand=_profile_hand(info.get("plays") or info.get("hand"))
    dob_token=_dob_token(data.get("birthday"))
    if profile_id != PROVIDER_NUMERIC_ID:
        raise ValueError("SHELBAYH_PROFILE_ID_MISMATCH")
    if _norm(profile_name) != _norm(PROVIDER_DISPLAY_NAME):
        raise ValueError("SHELBAYH_PROFILE_NAME_MISMATCH")
    if profile_ioc != CANONICAL_IOC:
        raise ValueError("SHELBAYH_PROFILE_IOC_MISMATCH")
    if hand != CANONICAL_HAND:
        raise ValueError("SHELBAYH_PROFILE_HAND_MISMATCH")
    if dob_token is None:
        raise ValueError("SHELBAYH_PROFILE_DOB_INVALID")
    dob=date(int(dob_token[:4]),int(dob_token[4:6]),int(dob_token[6:8]))

    history=_history_proof(history_csv,dob)
    ranking=_provider_ranking_proof(runtime_dir)
    r706=_r706_proof(r706_path)
    discarded=[key for key in ("currentRank","points","progress","careerMoney") if key in data]

    record={
        "provider_player_id":PROVIDER_ID,
        "provider_display_name":PROVIDER_DISPLAY_NAME,
        "canonical_name":CANONICAL_NAME,
        "provider_ioc_raw":CANONICAL_IOC,
        "provider_ioc_canonical":CANONICAL_IOC,
        "ranking_cut":"2026-09-21",
        "provider_rank":ranking["provider_rank"],
        "provider_rank_points":ranking["provider_rank_points"],
        "pre_cut_history":{
            "canonical_source_ids":[CANONICAL_SOURCE_ID],
            "canonical_iocs":[CANONICAL_IOC],
            "observed_hands":[CANONICAL_HAND],
            "rows":history["rows"],
            "latest_row_date":history["latest_row_date"],
        },
        "canonical_name_source":{
            "canonical_source_id":CANONICAL_SOURCE_ID,
            "path":str(history_csv),
            "rows":history["rows"],
            "latest_row_date":history["latest_row_date"],
            "strict_before_period":CUT_TOKEN,
            "alias_proof":"PROFILE_DOB_IOC_HAND_PLUS_CANONICAL_SOURCE_HISTORY_AGE_CONSISTENCY",
        },
        "biographical_candidates":[{
            "master_id":"RAPIDAPI_PROFILE_"+PROVIDER_NUMERIC_ID,
            "name":PROVIDER_DISPLAY_NAME,
            "hand":CANONICAL_HAND,
            "dob":dob_token,
            "ioc":CANONICAL_IOC,
            "height_cm":None,
            "wikidata_id":None,
            "provider_profile_sha256":_sha(profile),
        }],
        "biography_source":"RAPIDAPI_ULTRA_PROFILE_NUMERIC_ID_ALIAS_CERT",
        "authority_basis":"CERTIFIED_PROVIDER_ALIAS_TO_CANONICAL_SOURCE_AND_SEALED_R706",
        "sealed_r706_history":r706,
        "stats_rich_pre_cut_history":{
            "rows":history["rows"],
            "stats_rich_rows":history["stats_rich_rows"],
            "earliest_row_date":history["earliest_row_date"],
            "latest_row_date":history["latest_row_date"],
            "max_age_error_years":history["max_age_error_years"],
        },
        "profile_competitive_fields_discarded":discarded,
    }
    return {
        "schema":"MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_V1",
        "purpose":"Bind provider spelling alias Abedallah Shelbayh to canonical historical identity Abdullah Shelbayh/S0NV without name-only matching.",
        "strict_before_period":CUT_TOKEN,
        "records":[record],
        "provider_profile_network_calls":1,
        "post_cut_competitive_data_used":False,
        "outcomes_used":False,
        "odds_used":False,
        "metrics_opened":False,
        "automatic_wagering":False,
        "real_money":"BLOCKED",
    }


def main() -> None:
    key=os.environ.get("RAPIDAPI_TENNIS_KEY","").strip()
    if not key:
        raise SystemExit("RAPIDAPI_TENNIS_KEY_REQUIRED")
    client=RapidApiTennisClient(key)
    profile=client._get(f"/tennis/v2/atp/player/profile/{PROVIDER_NUMERIC_ID}")
    cert=build_certificate(
        profile=profile,
        history_csv=Path("evidence/cor0203/preholdout/2026_challenger_live_snapshot.csv"),
        runtime_dir=Path("evidence/cor0203/runtime"),
        r706_path=Path("evidence/cor0203/runtime/MATRIX_COR0203_R706_TARGET_HISTORY_READINESS_LAST.json"),
    )
    cert["provider_profile_network_calls"]=client.request_count
    out=Path("evidence/cor0203/identity/MATRIX_COR0203_CERTIFIED_IDENTITY_ALIASES_20261003.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(cert,indent=2,sort_keys=True,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "status":"PASS",
        "provider_player_id":PROVIDER_ID,
        "canonical_name":CANONICAL_NAME,
        "canonical_source_id":CANONICAL_SOURCE_ID,
        "history_rows":cert["records"][0]["stats_rich_pre_cut_history"]["rows"],
        "stats_rich_rows":cert["records"][0]["stats_rich_pre_cut_history"]["stats_rich_rows"],
        "r706_ready":cert["records"][0]["sealed_r706_history"]["fully_history_ready"],
        "provider_network_calls":client.request_count,
        "real_money":"BLOCKED",
    },sort_keys=True))


if __name__=="__main__":
    main()
