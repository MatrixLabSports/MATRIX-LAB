"""Offline SHA-bound Challenger visible-profile audit; never admits model rows."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

BASE = Path("evidence/tennis_calendar_physical")
REPORT = "MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_LAST.json"
SCHEMA = "MATRIX_TENNIS_FREE_PROFILE_SOURCE_BINDING_AUDIT_V1"

def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def utc(v: str) -> datetime:
    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("PROFILE_AUDIT_TIMESTAMP_HAS_NO_TIMEZONE")
    return dt.astimezone(timezone.utc)

def source_bound_detail(folder: Path, declared_digest: str) -> tuple[dict, bytes, Path, bool]:
    """Use only exact SHA-matching original capture or its immutable archive.

    A current LAST must never replace a different source used by a previous
    prematch biography. Missing original bytes fail closed, no guessed match.
    """
    if not re.fullmatch(r"[0-9a-f]{64}", str(declared_digest or "")):
        raise ValueError("PROFILE_AUDIT_DECLARED_DETAIL_SHA_MISSING")
    current = folder / "sofascore_verified_match_details.json"
    if current.is_file():
        raw = current.read_bytes()
        if len(raw) > 7_000_000:
            raise ValueError("PROFILE_AUDIT_OVERSIZED")
        if sha(raw) == declared_digest:
            return json.loads(raw), raw, current, False
    archive = folder / "archive"
    if archive.is_dir():
        candidates = sorted(
            p for p in archive.glob("*.json")
            if p.name.startswith((
                "MATRIX_TENNIS_SOURCE_DETAILS_",
                "MATRIX_TENNIS_MATCH_DETAIL_CAPTURE_ATTEMPT_",
                "sofascore_verified_match_details_",
            ))
        )
        if len(candidates) > 250:
            raise ValueError("PROFILE_AUDIT_ARCHIVE_TOO_LARGE")
        for candidate in candidates:
            if candidate.stat().st_size > 7_000_000:
                continue
            raw = candidate.read_bytes()
            if sha(raw) == declared_digest:
                return json.loads(raw), raw, candidate, True
    raise ValueError("PROFILE_AUDIT_ORIGINAL_DETAIL_SHA_SNAPSHOT_UNAVAILABLE")


def audit(root: Path, day: str) -> dict:
    date.fromisoformat(day)
    folder = root / BASE / day
    a_path = folder / "MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH.json"
    a_bytes = a_path.read_bytes()
    if len(a_bytes) > 7_000_000:
        raise ValueError("PROFILE_AUDIT_OVERSIZED")
    profiles = json.loads(a_bytes)
    detail, d_bytes, detail_path, archived_detail_used = source_bound_detail(
        folder, profiles.get("source_detail_sha256")
    )
    if (profiles.get("schema") != "MATRIX_TENNIS_FREE_VISIBLE_PROFILE_BIRTHDATES_RESEARCH_V1"
        or detail.get("schema") != "MATRIX_OPERA_TENNIS_MATCH_DETAIL_OBSERVATION_V1"
        or profiles.get("target_date_bogota") != day
        or detail.get("target_date_bogota") != day
        or profiles.get("source_detail_sha256") != sha(d_bytes)
        or profiles.get("real_money") != "BLOCKED"
        or detail.get("real_money") != "BLOCKED"
        or profiles.get("official_holdout_admitted") != 0
        or detail.get("new_model_observations_admitted") != 0
        or profiles.get("provider_identity_equivalence_certified") is not False
        or detail.get("provider_identity_equivalence_certified") is not False):
        raise ValueError("PROFILE_AUDIT_ORIGINAL_SOURCE_BINDING_FAILED")
    events = detail.get("events")
    observed = profiles.get("profiles")
    if not isinstance(events,list) or not isinstance(observed,list):
        raise ValueError("PROFILE_AUDIT_ROWS_MISSING")
    index = {}
    for event in events:
        if event.get("surface") not in ("Hard", "Clay"):
            raise ValueError("PROFILE_AUDIT_SURFACE_AMBIGUOUS")
        kickoff = utc(event["kickoff_utc"])
        if kickoff.date() < date.fromisoformat(day):
            raise ValueError("PROFILE_AUDIT_KICKOFF_DAY_INCONSISTENT")
        for player in event.get("players") or []:
            pid = str(player.get("sofascore_player_id") or "")
            if not pid.isdecimal() or pid in index:
                raise ValueError("PROFILE_AUDIT_DUPLICATE_PLAYER_ID")
            index[pid] = (event, player)
    result = []
    seen = set()
    for p in observed:
        pid = str(p.get("sofascore_player_id") or "")
        if pid in seen:
            raise ValueError("PROFILE_AUDIT_DUPLICATE_PROFILE")
        seen.add(pid)
        event_player = index.get(pid)
        if event_player is None:
            raise ValueError("PROFILE_AUDIT_PROFILE_NOT_ON_CAPTURED_MATCH")
        event, player = event_player
        if (str(p.get("name")) != str(player.get("name"))
            or str(p.get("country")) != str(player.get("country"))
            or str(p.get("profile_url")) != str(player.get("profile_url"))
            or str(p.get("surface")) != str(event.get("surface"))
            or utc(p.get("kickoff_utc")) != utc(event["kickoff_utc"])
            or utc(p.get("observed_at_utc")) >= utc(event["kickoff_utc"])):
            raise ValueError("PROFILE_AUDIT_PLAYER_OR_PIT_CONFLICT")
        dob = str(p.get("visible_birth_date_yyyymmdd") or "")
        if not re.fullmatch(r"\d{8}", dob):
            raise ValueError("PROFILE_AUDIT_BIRTHDATE_FORMAT")
        date(int(dob[:4]),int(dob[4:6]),int(dob[6:]))
        origin = p.get("original_match_research") or {}
        historical = int(origin.get("pre_cut_latest_row_date") or 0)
        cutoff = int(day.replace("-", ""))
        if historical >= cutoff or historical <= 0:
            raise ValueError("PROFILE_AUDIT_PRECUT_HISTORY_NOT_PRECUT")
        if p.get("approved_model_player_id") is not False:
            raise ValueError("PROFILE_AUDIT_MODEL_PLAYER_PREMATURELY_APPROVED")
        result.append({
            "sofascore_player_id":pid,"sofascore_event_id":event["sofascore_event_id"],
            "name":p["name"],"surface":event["surface"],
            "visible_birth_date_yyyymmdd":dob,
            "historical_source_id_research_only":origin.get("pre_cut_source_id"),
            "historical_pre_cut_rows_research_only":origin.get("pre_cut_rows"),
            "source_identity_certified":False,"model_pit_certified":False,
            "official_holdout_admitted":False
        })
    return {
        "schema":SCHEMA,"date_bogota":day,
        "status":"VISIBLE_BIOGRAPHY_SOURCE_BOUND_RESEARCH_ONLY",
        "profiles_verified_against_match_details":len(result),
        "matches_with_verified_profiles":len({r["sofascore_event_id"] for r in result}),
        "archived_original_detail_used":archived_detail_used,
        "source_detail_path":str(detail_path.relative_to(root)).replace(chr(92),"/"),
        "source_sha256":{"visible_profiles":sha(a_bytes),"verified_match_details":sha(d_bytes)},
        "independent_provider_player_id_certified":False,
        "original_model_pit_equivalence_certified":False,
        "new_hard_holdout_observations":0,"new_clay_holdout_observations":0,
        "telegram_signal_authorized":False,"automatic_wagering":False,
        "real_money":"BLOCKED","rows":result
    }

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument("--date",required=True)
    ap.add_argument("--root",type=Path,default=Path("."))
    args=ap.parse_args()
    report=audit(args.root,args.date)
    # The governed free-intake workflow persists only reconciliation outputs.
    # Keep browser source bytes read-only and archive this independent audit
    # alongside other research reports, never inside Hard/Clay holdouts.
    path=args.root/"evidence/tennis_calendar_reconciliation"/args.date/REPORT
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"day":args.date,"source_bound_profiles":report["profiles_verified_against_match_details"],
                      "admitted":0,"status":report["status"]},sort_keys=True))

if __name__=="__main__":
    main()
