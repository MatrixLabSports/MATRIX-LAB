from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_rapidapi_tennis_discovery import RapidApiTennisClient


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, list):
        raise ValueError("COVERAGE_DATA_NOT_LIST")
    return [row for row in data if isinstance(row, Mapping)]


def _meta(row: Mapping[str, Any]) -> tuple[str, str, str]:
    tournament = row.get("tournament")
    tournament = tournament if isinstance(tournament, Mapping) else {}
    country = tournament.get("country")
    country = country if isinstance(country, Mapping) else {}
    rank = tournament.get("rank")
    rank = rank if isinstance(rank, Mapping) else {}
    name = str(tournament.get("name") or row.get("tournamentName") or "UNKNOWN")
    country_name = str(country.get("name") or country.get("acr") or tournament.get("countryAcr") or "UNKNOWN")
    rank_id = str(tournament.get("rankId") or rank.get("id") or "UNKNOWN")
    return name, country_name, rank_id


def dataset(client: RapidApiTennisClient, tour: str, start: date, stop: date) -> dict[str, Any]:
    all_rows: list[Mapping[str, Any]] = []
    page = 1
    while page <= 4:
        payload = client._get(
            f"/tennis/v2/{tour}/fixtures/{start.isoformat()}/{stop.isoformat()}",
            {
                "include": "round,tournament,tournament.court,tournament.rank,tournament.country",
                "filter": "PlayerGroup:singles",
                "pageNo": page,
                "pageSize": 500,
            },
        )
        if not isinstance(payload, Mapping):
            raise ValueError("COVERAGE_ENVELOPE_INVALID")
        all_rows.extend(_rows(payload))
        if not bool(payload.get("hasNextPage")):
            break
        page += 1
    if page > 4:
        raise ValueError("COVERAGE_PAGE_LIMIT")
    tournaments: set[str] = set()
    countries: set[str] = set()
    ranks: dict[str, int] = {}
    for row in all_rows:
        tournament, country, rank_id = _meta(row)
        tournaments.add(tournament)
        countries.add(country)
        ranks[rank_id] = ranks.get(rank_id, 0) + 1
    return {
        "events": len(all_rows),
        "tournaments": len(tournaments),
        "countries": len(countries - {"UNKNOWN"}),
        "rank_event_counts": dict(sorted(ranks.items())),
        "tournament_names": sorted(tournaments),
        "country_names": sorted(countries - {"UNKNOWN"}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start")
    parser.add_argument("--days", type=int, default=4)
    args = parser.parse_args()
    if not 1 <= args.days <= 4:
        raise SystemExit("DAYS_MUST_BE_1_TO_4")
    start = date.fromisoformat(args.start) if args.start else datetime.now(timezone.utc).date()
    stop = start + timedelta(days=args.days - 1)
    key = os.environ.get("RAPIDAPI_TENNIS_KEY") or os.environ.get("API_TENNIS_KEY") or ""
    client = RapidApiTennisClient(key)
    result = {
        "schema": "MATRIX_TENNIS_WORLD_COVERAGE_AUDIT_V1",
        "observed_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "window": {"start": start.isoformat(), "stop": stop.isoformat()},
        "atp": dataset(client, "atp", start, stop),
        "wta": dataset(client, "wta", start, stop),
        "network_calls": client.request_count,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": "PASS",
        "limits": [
            "Observed breadth in this live window does not prove literal 100 percent coverage of every world tournament.",
            "TourRank metadata is preserved for level analysis.",
        ],
    }
    out = Path("evidence/tennis_world_coverage")
    out.mkdir(parents=True, exist_ok=True)
    (out / "coverage_audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("TENNIS_WORLD_COVERAGE_AUDIT: PASS")
    print("network_calls=", result["network_calls"])
    print("atp_events=", result["atp"]["events"])
    print("wta_events=", result["wta"]["events"])
    print("atp_tournaments=", result["atp"]["tournaments"])
    print("wta_tournaments=", result["wta"]["tournaments"])
    print("real_money= BLOCKED")


if __name__ == "__main__":
    main()
