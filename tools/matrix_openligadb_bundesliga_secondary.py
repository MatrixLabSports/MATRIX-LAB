"""Additional FREE Bundesliga identity crosscheck, never new official P_MATRIX.

SofaScore and Flashscore retain priority. This is a secondary, open-licensed
independent calendar/fixture research source after the first two providers.
Only exact same-league, same-UTC-kickoff, same-oriented-team evidence passes.
No match from another provider is silently treated as identical, no historical
results may be backfilled into a prematch probability, and no betting actions.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
SOURCE_BASE = "https://api.openligadb.de/getmatchdata/bl1"
MAX_SOURCE_BYTES = 4_000_000
SCHEMA = "MATRIX_BUNDESLIGA_OPENLIGADB_INDEPENDENT_SECONDARY_V1"

def aware(value: str) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("INDEPENDENT_SOURCE_NAIVE_KICKOFF")
    return dt.astimezone(timezone.utc)

def normalized(name: str) -> str:
    t = unicodedata.normalize("NFKD", str(name or ""))
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()

def match(intake: dict, season: list, *, captured_at: datetime,
          raw_sha256: str) -> dict:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("SOURCE_CAPTURE_TIME_REQUIRED")
    now = captured_at.astimezone(timezone.utc)
    if (intake.get("schema") != "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
        or intake.get("provider_status") != "AUTHENTICATED_FIXTURE_CAPTURE"
        or intake.get("source") != "FOOTBALL_DATA_ORG"
        or intake.get("real_money") != "BLOCKED"
        or intake.get("signal_generation_authorized") is not False):
        raise ValueError("SECONDARY_INTAKE_NOT_AUTHENTIC")
    day = intake.get("target_date_bogota")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", str(day or "")):
        raise ValueError("SECONDARY_TARGET_DAY_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", raw_sha256):
        raise ValueError("SECONDARY_RAW_SOURCE_SHA_MISSING")
    if not isinstance(season, list):
        raise ValueError("SECONDARY_LEAGUE_RESPONSE_MUST_BE_LIST")
    date_value = datetime.fromisoformat(str(day)).date()
    season_start = date_value.year if date_value.month >= 7 else date_value.year - 1
    candidates = [r for r in intake.get("fixtures", []) if
                  isinstance(r, dict) and r.get("source_competition_id") == 2002]
    if len({str(r.get("source_fixture_id")) for r in candidates}) != len(candidates):
        raise ValueError("PRIMARY_BUNDESLIGA_IDS_DUPLICATE")
    source = {}
    for row in season:
        if not isinstance(row, dict):
            continue
        if row.get("leagueShortcut") != "bl1" or row.get("leagueSeason") != season_start:
            continue
        if not isinstance(row.get("matchID"), int) or row.get("matchID") <= 0:
            continue
        home, away = row.get("team1") or {}, row.get("team2") or {}
        if not (isinstance(home, dict) and isinstance(away, dict)):
            continue
        if not all(str(r.get("teamName") or "").strip() for r in (home, away)):
            continue
        try:
            kickoff = aware(row["matchDateTimeUTC"])
        except (KeyError, ValueError, TypeError):
            continue
        key = (normalized(home["teamName"]), normalized(away["teamName"]), kickoff)
        source.setdefault(key, []).append(row)
    matched, rejected = [], []
    used_secondary_ids = set()
    for p in candidates:
        try:
            if p.get("signal_generation_authorized") is not False:
                raise ValueError("PRIMARY_FIXTURE_NOT_FAIL_CLOSED")
            kickoff = aware(p["kickoff_utc"])
            if kickoff.astimezone(BOGOTA).date().isoformat() != day:
                raise ValueError("TARGET_DATE_MISMATCH")
            key = (normalized(p.get("home")), normalized(p.get("away")), kickoff)
            hits = source.get(key, [])
            if len(hits) != 1:
                raise ValueError("MISSING_OR_AMBIGUOUS_EXACT_SECONDARY_MATCH")
            row = hits[0]
            sid = str(row["matchID"])
            if sid in used_secondary_ids:
                raise ValueError("SECONDARY_ID_REUSED")
            if row.get("matchIsFinished") is not False:
                raise ValueError("SECONDARY_MATCH_NOT_PREMATCH")
            if now >= kickoff:
                raise ValueError("SECONDARY_CAPTURE_AFTER_KICKOFF")
            used_secondary_ids.add(sid)
            matched.append({
                "primary_fixture_id": str(p["source_fixture_id"]),
                "secondary_match_id": sid,
                "home": p["home"], "away": p["away"],
                "kickoff_utc": kickoff.isoformat(),
                "team_order_exact": True, "utc_kickoff_exact": True,
                "independent_calendar_identity_verified": True,
                "original_enriched_feature_parity_certified": False,
                "original_p_matrix_authorized": False,
                "telegram_signal_authorized": False,
            })
        except (ValueError, KeyError, TypeError) as e:
            rejected.append({
                "primary_fixture_id": str(p.get("source_fixture_id")),
                "reason": str(e),
                "signal_generation_authorized": False,
            })
    return {
        "schema": SCHEMA,
        "status": "EXACT_SECONDARY_PREMATCH_MATCHES_RESEARCH_ONLY"
                  if matched else "NO_EXACT_SECONDARY_MATCHES_FAIL_CLOSED",
        "captured_at_utc": now.isoformat(),
        "target_date_bogota": day,
        "source": "OPENLIGADB_BUNDESLIGA_BL1_" + str(season_start),
        "independent_source_uri": SOURCE_BASE + "/" + str(season_start),
        "independent_raw_payload_sha256": raw_sha256,
        "primary_provider": "FOOTBALL_DATA_ORG",
        "source_priority": ["SofaScore", "Flashscore",
                            "football-data.org", "OpenLigaDB"],
        "primary_bundesliga_candidates": len(candidates),
        "season_records_received": len(season),
        "exact_prematch_matches": len(matched),
        "rejected_candidates": len(rejected),
        "matched": matched,
        "rejected": rejected,
        "metadata_only_crosscheck": True,
        "cross_provider_team_id_equivalence_certified": False,
        "original_enriched_feature_parity_certified": False,
        "original_six_league_equivalence_certified": False,
        "production_p_matrix_authorized": False,
        "telegram_signal_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }

def fetch(*, season_start: int = 2026, opener=urlopen) -> tuple[list, bytes]:
    if not (2020 <= season_start <= 2100):
        raise ValueError("SOURCE_SEASON_INVALID")
    url = SOURCE_BASE + "/" + str(season_start)
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "MATRIX-LAB-Research/1.0 (+https://github.com/MatrixLabSports/MATRIX-LAB)",
    })
    try:
        with opener(req, timeout=18) as response:
            if int(response.status) != 200:
                raise ValueError("SECONDARY_HTTP_NOT_200")
            raw = response.read(MAX_SOURCE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        raise ValueError("SECONDARY_FREE_PROVIDER_UNAVAILABLE") from e
    if not raw or len(raw) > MAX_SOURCE_BYTES:
        raise ValueError("SECONDARY_SOURCE_EMPTY_OR_OVERSIZED")
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as e:
        raise ValueError("SECONDARY_SOURCE_INVALID_JSON") from e
    if not isinstance(parsed, list):
        raise ValueError("SECONDARY_SOURCE_WRONG_SHAPE")
    return parsed, raw

def main() -> None:
    arg = argparse.ArgumentParser()
    arg.add_argument("--intake", type=Path, required=True)
    arg.add_argument("--out", type=Path, required=True)
    args = arg.parse_args()
    intake = json.loads(args.intake.read_bytes())
    target_day = datetime.fromisoformat(str(intake["target_date_bogota"])).date()
    season_start = target_day.year if target_day.month >= 7 else target_day.year - 1
    season, raw = fetch(season_start=season_start)
    sha = hashlib.sha256(raw).hexdigest()
    out = match(intake, season, captured_at=datetime.now(timezone.utc),
                raw_sha256=sha)
    # Evidence in a sibling research report; never persist to model manifests
    # or Telegram production archives.
    if args.out.name != "MATRIX_OPENLIGADB_SECONDARY_CROSSCHECK.json":
        raise SystemExit("SECONDARY_OUTPUT_MUST_BE_RESEARCH_ONLY")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Preserve source bytes independently of our parsed assertions so another
    # auditor can reproduce the match rather than trusting an asserted digest.
    raw_dir = args.out.parent / "sources"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / ("openligadb_bl1_" + sha + ".json")
    if raw_file.exists():
        if raw_file.read_bytes() != raw:
            raise ValueError("SECONDARY_IMMUTABLE_SOURCE_HASH_CONFLICT")
    else:
        with raw_file.open("xb") as handle:
            handle.write(raw)
    out["independent_raw_source_path"] = str(raw_file)
    args.out.write_text(json.dumps(out, ensure_ascii=False, indent=2,
                                  sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: out[k] for k in (
        "status", "primary_bundesliga_candidates", "exact_prematch_matches",
        "rejected_candidates", "production_p_matrix_authorized",
        "telegram_signal_authorized")}, sort_keys=True))

if __name__ == "__main__":
    main()
