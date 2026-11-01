"""Fail-closed independent fixture intake for MATRIX.

Consumes *locally captured* authorized SofaScore/Flashscore snapshots only.
It does not scrape sites, call paid providers, calculate P_MATRIX or send bets.
Output is a discovery sidecar, deliberately outside Telegram candidate paths.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
ALLOWED = ("SofaScore", "Flashscore")
SCHEMA = "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"


def _utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("KICKOFF_UTC_REQUIRED")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("KICKOFF_MUST_HAVE_TIMEZONE")
    return parsed.astimezone(timezone.utc)


def ingest(snapshots: list[dict], *, now_utc: datetime | None = None) -> dict:
    now = now_utc or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError("NOW_MUST_HAVE_TIMEZONE")
    now = now.astimezone(timezone.utc)
    accepted = {}
    rejected = []
    for index, item in enumerate(snapshots):
        if not isinstance(item, dict):
            rejected.append({"index": index, "reason": "INVALID_SNAPSHOT"})
            continue
        provider = item.get("provider")
        if provider not in ALLOWED:
            rejected.append({"index": index, "reason": "UNAUTHORIZED_SOURCE"})
            continue
        if item.get("capture_authorized") is not True or item.get("physical_capture_verified") is not True:
            rejected.append({"index": index, "reason": "CAPTURE_NOT_VERIFIED"})
            continue
        if not isinstance(item.get("source_url"), str) or not item["source_url"].startswith("https://"):
            rejected.append({"index": index, "reason": "SOURCE_URL_REQUIRED"})
            continue
        if not isinstance(item.get("captured_at_utc"), str):
            rejected.append({"index": index, "reason": "CAPTURE_TIME_REQUIRED"})
            continue
        try:
            captured = _utc(item["captured_at_utc"])
        except ValueError:
            rejected.append({"index": index, "reason": "INVALID_CAPTURE_TIME"})
            continue
        if captured > now or (now - captured).total_seconds() > 3600:
            rejected.append({"index": index, "reason": "STALE_OR_FUTURE_CAPTURE"})
            continue
        fixtures = item.get("fixtures")
        if not isinstance(fixtures, list):
            rejected.append({"index": index, "reason": "FIXTURES_NOT_LIST"})
            continue
        for j, row in enumerate(fixtures):
            if not isinstance(row, dict):
                rejected.append({"index": index, "fixture_index": j, "reason": "INVALID_FIXTURE"})
                continue
            home, away = row.get("home"), row.get("away")
            if not all(isinstance(v, str) and v.strip() for v in (home, away)) or home.strip().casefold() == away.strip().casefold():
                rejected.append({"index": index, "fixture_index": j, "reason": "INVALID_TEAMS"})
                continue
            try:
                kickoff = _utc(row.get("kickoff_utc"))
            except ValueError:
                rejected.append({"index": index, "fixture_index": j, "reason": "INVALID_KICKOFF"})
                continue
            if kickoff <= now:
                rejected.append({"index": index, "fixture_index": j, "reason": "ALREADY_STARTED"})
                continue
            # Cross-provider fixture ids are not interchangeable. Use a transparent
            # team/time key for discovery deduplication, not betting settlement.
            key = "|".join((home.strip().casefold(), away.strip().casefold(), kickoff.isoformat()))
            if key in accepted:
                accepted[key]["source_providers"].append(provider)
                continue
            accepted[key] = {
                "home": home.strip(), "away": away.strip(),
                "kickoff_utc": kickoff.isoformat(),
                "kickoff_bogota": kickoff.astimezone(BOGOTA).isoformat(),
                "source_providers": [provider],
                "source_url": item["source_url"],
                "captured_at_utc": captured.isoformat(),
                "p_matrix": None, "decimal_odds": None,
                "signal_generation_authorized": False,
            }
    rows = sorted(accepted.values(), key=lambda r: (r["kickoff_utc"], r["home"], r["away"]))
    return {
        "schema": SCHEMA,
        "status": "DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES",
        "fixtures": rows, "accepted_count": len(rows), "rejected": rejected,
        "provider_network_calls": 0, "telegram_messages_sent": 0,
        "real_money": "BLOCKED", "automatic_wagering": False,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Local JSON list of authorized physical browser snapshots")
    p.add_argument("--out", required=True, help="Discovery sidecar path; not a Telegram candidate path")
    args = p.parse_args()
    output = Path(args.out)
    if "daily_prematch_reports" in output.parts or "tennis_signals" in output.parts:
        raise SystemExit("DISCOVERY_SIDECAR_CANNOT_WRITE_SIGNAL_CANDIDATES")
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise SystemExit("INPUT_MUST_BE_SNAPSHOT_LIST")
    result = ingest(raw)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "accepted_count": result["accepted_count"]}))


if __name__ == "__main__":
    main()
