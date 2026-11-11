"""Deterministic, offline free-provider candidate ledger (Hard/Clay).

Audits each actual Live Tennis API fixture against frozen browser-first
source hashes and exact browser name hints. Never admits a model row or
changes calibrated state. Missing PIT, precise independent clock, and
provider-player crosswalk remain explicit per-fixture blockers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SCHEMA = "MATRIX_TENNIS_FREE_CANDIDATE_DECISIONS_V1"
COVERAGE = Path("evidence/free_providers")
RECONCILIATION = Path("evidence/tennis_calendar_reconciliation")
BROWSER = Path("evidence/tennis_calendar_physical")


def load(root: Path, path: Path):
    f = root / path
    raw = f.read_bytes()
    if len(raw) > 4_000_000:
        raise ValueError("EVIDENCE_OVERSIZE:" + str(path))
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def utc(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NAIVE_UTC_DATETIME")
    return dt.astimezone(timezone.utc)


def surname(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii")
    tokens = re.findall(r"[a-z0-9]+", normalized.casefold())
    return tokens[-1] if tokens else ""


def evaluate(root: Path, day: str, now: datetime) -> dict:
    start_day = date.fromisoformat(day)
    if now.tzinfo is None:
        raise ValueError("EVALUATION_CLOCK_WITHOUT_TIMEZONE")
    now = now.astimezone(timezone.utc)
    snapshot, snapshot_hash = load(root, COVERAGE / day / "MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT.json")
    cross, cross_hash = load(root, RECONCILIATION / day / "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH.json")
    if (snapshot.get("schema") != "MATRIX_FREE_PROVIDER_COVERAGE_SNAPSHOT_V1"
            or snapshot.get("target_date_bogota") != day
            or snapshot.get("status") != "PASS"
            or snapshot.get("protections", {}).get("real_money") != "BLOCKED"
            or snapshot.get("promotion", {}).get("automatic_model_feed") is not False
            or snapshot.get("promotion", {}).get("automatic_counter_increment") is not False
            or cross.get("schema") != "MATRIX_TENNIS_EXACT_BROWSER_CROSSMATCH_V1"
            or cross.get("target_date_bogota") != day
            or cross.get("real_money") != "BLOCKED"
            or cross.get("hard_holdout_admitted") != 0
            or cross.get("clay_holdout_admitted") != 0
            or cross.get("source_event_equivalence_certified") is not False):
        raise ValueError("UNTRUSTED_PROSPECTIVE_EVIDENCE")
    api = snapshot.get("providers", {}).get("live_tennis_api", {})
    if (api.get("request", {}).get("http_status") != 200
            or not api.get("authenticated")
            or api.get("world_complete") is not False):
        raise ValueError("FREE_PROVIDER_NOT_AUTHENTICATED")
    at_api = utc(snapshot["generated_at_utc"])
    if at_api > now + timedelta(minutes=2):
        raise ValueError("FREE_SNAPSHOT_FROM_FUTURE")
    source_times = {}
    source_hashes = {}
    for label, filename in (("SOFASCORE", "sofascore_opera_full_link_observations.json"),
                            ("FLASHSCORE", "flashscore_opera_full_link_observations.json")):
        source, source_sha = load(root, BROWSER / day / filename)
        if (source.get("schema") != "MATRIX_OPERA_TENNIS_EVENT_LINK_CAPTURE_V1"
                or source.get("target_date_bogota") != day
                or source.get("source") != label
                or source.get("real_money") != "BLOCKED"
                or source.get("canonical_fixture_export_authorized") is not False
                or source.get("individual_match_date_verified") is not False
                or cross.get("source_capture_sha256", {}).get(label) != source_sha):
            raise ValueError("BROWSER_SOURCE_SHA_OR_GOVERNANCE_MISMATCH:" + label)
        source_times[label] = utc(source["collected_at_utc"])
        source_hashes[label] = source_sha
    exact_hints = cross.get("matches") or []
    if not isinstance(exact_hints, list):
        raise ValueError("INVALID_EXACT_HINTS")
    candidate_lists = {"Hard": api.get("d0_d2_hard_candidates"),
                       "Clay": api.get("d0_d2_clay_candidates")}
    records = []
    seen = set()
    for surface, items in candidate_lists.items():
        if not isinstance(items, list) or len(items) > 400:
            raise ValueError("MISSING_OR_OVERSIZE_SURFACE_CANDIDATES:" + surface)
        declared = api.get("d0_d2_" + surface.lower() + "_rows")
        if declared != len(items):
            raise ValueError("SURFACE_COUNT_MISMATCH:" + surface)
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("INVALID_PROVIDER_ROW")
            pid = item.get("provider_match_id")
            if not isinstance(pid, int) or pid <= 0 or pid in seen:
                raise ValueError("DUPLICATE_OR_INVALID_PROVIDER_MATCH_ID")
            seen.add(pid)
            if str(item.get("surface") or "").casefold() != surface.casefold():
                raise ValueError("PROVIDER_SURFACE_MISMATCH")
            players = [str(item.get(k) or "").strip() for k in ("player1_name", "player2_name")]
            event_clock = utc(item["start_time_utc"]) if item.get("start_time_utc") else None
            match_day = event_clock.astimezone(BOGOTA).date() if event_clock else None
            candidate_day = item.get("bogota_date")
            blockers = [
                "MODEL_PROVIDER_PLAYER_IDENTITY_NOT_CERTIFIED",
                "INDEPENDENT_PER_EVENT_KICKOFF_NOT_CERTIFIED",
                "CURRENT_PREMATCH_PIT_HISTORY_NOT_CERTIFIED",
                "SURFACE_SOURCE_INDEPENDENCE_NOT_CERTIFIED",
            ]
            if not all(players) or players[0] == players[1]:
                blockers.append("MISSING_OR_REPEATED_PLAYER_NAME")
            if event_clock is None or match_day is None or not (start_day <= match_day <= start_day + timedelta(days=2)) or candidate_day != match_day.isoformat():
                blockers.append("INVALID_OR_OUT_OF_SCOPE_LOCAL_KICKOFF")
            if str(item.get("status", "")).casefold() != "scheduled":
                blockers.append("PROVIDER_NOT_SCHEDULED_PREMATCH")
            if event_clock and at_api >= event_clock:
                blockers.append("API_SNAPSHOT_AT_OR_AFTER_KICKOFF")
            if event_clock and now >= event_clock:
                blockers.append("PROSPECTIVE_WINDOW_CLOSED")
            if event_clock and any(at >= event_clock for at in source_times.values()):
                blockers.append("BROWSER_LINK_SNAPSHOT_AT_OR_AFTER_KICKOFF")
            surnames = [surname(x) for x in players]
            name_matches = [
                x for x in exact_hints
                if (isinstance(x, dict) and
                    len(surnames) == 2 and surnames[0] and surnames[1]
                    and surnames[0] != surnames[1]
                    and all(s in str(x.get("source_name_token_key") or "").split() for s in surnames))
            ]
            hint = name_matches[0] if len(name_matches) == 1 else None
            if hint is None:
                blockers.append("NO_UNAMBIGUOUS_TWO_BROWSER_NAME_HINT")
            if hint is not None:
                blockers.append("BROWSER_NAME_HINT_NOT_FIXTURE_CERTIFICATION")
            records.append({
                "source": "LIVE_TENNIS_API",
                "source_match_id": pid,
                "provider_status": item.get("status"),
                "surface": surface,
                "tournament": item.get("tournament"),
                "player1": players[0],
                "player2": players[1],
                "provider_kickoff_utc": event_clock.isoformat() if event_clock else None,
                "bogota_day": candidate_day,
                "browser_name_hint_only": {
                    "sofascore_id": hint.get("sofascore_id"),
                    "flashscore_mid": hint.get("flashscore_mid"),
                    "sofascore_url": hint.get("sofascore_url"),
                    "flashscore_url": hint.get("flashscore_url"),
                } if hint else None,
                "independent_clock_certified": False,
                "original_model_feature_parity": False,
                "official_holdout_admitted": False,
                "telegram_signal_authorized": False,
                "decision": "BLOCKED_NOT_PROSPECTIVE_MODEL_ADMISSIBLE",
                "blockers": sorted(set(blockers)),
            })
    counts = Counter(x["surface"] for x in records)
    hints = sum(x["browser_name_hint_only"] is not None for x in records)
    return {
        "schema": SCHEMA,
        "target_date_bogota": day,
        "evaluated_at_utc": now.isoformat(),
        "source_sha256": {"free_snapshot": snapshot_hash, "exact_name_crossmatch": cross_hash, **source_hashes},
        "source_capture_utc": {k: v.isoformat() for k, v in source_times.items()},
        "status": "RESEARCH_CANDIDATES_TRIAGED_NO_MODEL_ADMISSION",
        "hard_provider_candidates": counts["Hard"],
        "clay_provider_candidates": counts["Clay"],
        "two_browser_name_hints_only": hints,
        "records": records,
        "hard_new_holdout_admissions": 0,
        "clay_new_holdout_admissions": 0,
        "model_parameters_modified": False,
        "paid_api_used": False,
        "real_money": "BLOCKED",
        "automatic_wagering": False,
        "telegram_signal_authorized": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--root", type=Path, default=Path.cwd())
    a = p.parse_args()
    report = evaluate(a.root, a.date, datetime.now(timezone.utc))
    out = a.root / RECONCILIATION / a.date / "MATRIX_TENNIS_FREE_CANDIDATE_DECISIONS_LAST.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "hard_provider_candidates",
        "clay_provider_candidates", "two_browser_name_hints_only",
        "hard_new_holdout_admissions", "clay_new_holdout_admissions")}, sort_keys=True))


if __name__ == "__main__":
    main()
