from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.football_clv_odds_api_net_capture import _extract_total_25, _sim

ODDS_API_BASE = "https://api.odds-api.net/v1"
MAX_SAMPLE = 12
STRICT_FRESH_SECONDS = 120


def _aware(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def run(*, api_key: str, now: datetime | None = None, session: Any | None = None, sample_size: int = MAX_SAMPLE) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("ODDS_API_NET_KEY_NOT_CONFIGURED")
    if not (1 <= sample_size <= MAX_SAMPLE):
        raise ValueError("SAMPLE_SIZE_OUT_OF_POLICY")

    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    bundle, manifest = load_chunked_canonical_bundle(Path("evidence/api_football/canonical_analysis"))
    coverage_path = Path("evidence/api_football/pinnacle_coverage/manifest.json")
    coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    covered_fixture_ids = {
        str(row.get("fixture_id"))
        for row in coverage.get("fixtures", [])
        if isinstance(row, Mapping) and row.get("has_pinnacle_odds") is True
    }
    ready = [
        row for row in bundle.get("inputs", [])
        if (
            isinstance(row, Mapping)
            and _aware(row["kickoff_utc"]) > reference
            and str(row.get("fixture_id")) in covered_fixture_ids
        )
    ]
    ready.sort(key=lambda row: (_aware(row["kickoff_utc"]), str(row.get("fixture_id"))))
    sample = ready[:sample_size]

    client = session or requests.Session()
    headers = {"X-API-Key": key, "Accept": "application/json"}
    rows: list[dict[str, Any]] = []
    calls = 0

    for row in sample:
        fixture_id = str(row.get("fixture_id"))
        kickoff = _aware(row["kickoff_utc"])
        home = str(row.get("home_team_name") or "")
        away = str(row.get("away_team_name") or "")
        start = int(kickoff.timestamp())

        er = client.get(
            ODDS_API_BASE + "/events",
            headers=headers,
            params={
                "sport": "soccer",
                "start_from": start - 900,
                "start_to": start + 900,
                "limit": 100,
                "include_bookmaker_ids": "true",
            },
            timeout=(10, 30),
        )
        calls += 1
        try:
            ep = er.json()
        except Exception:
            ep = {}
        events = ep.get("items") if isinstance(ep, Mapping) else []
        scored = []
        for event in events or []:
            if not isinstance(event, Mapping):
                continue
            direct = (_sim(home, event.get("home_team")) + _sim(away, event.get("away_team"))) / 2.0
            swapped = (_sim(home, event.get("away_team")) + _sim(away, event.get("home_team"))) / 2.0
            scored.append((max(direct, swapped), direct >= swapped, event))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0] if scored else None
        second = scored[1][0] if len(scored) > 1 else 0.0

        base = {
            "fixture_id": fixture_id,
            "kickoff_utc": kickoff.isoformat(),
            "home_team": home,
            "away_team": away,
            "identity_score": None if best is None else round(float(best[0]), 6),
            "second_identity_score": round(float(second), 6),
            "odds_api_event_id": None,
            "provider_quote_updated_at_utc": None,
            "provider_quote_age_seconds": None,
            "over_2_5_decimal_odds": None,
            "under_2_5_decimal_odds": None,
            "fresh_120s": False,
            "status": "BLOCKED_IDENTITY",
        }
        if er.status_code >= 300 or best is None or best[0] < 0.85 or (len(scored) > 1 and best[0] - second < 0.05):
            rows.append(base)
            continue

        event_id = str(best[2].get("event_id") or "")
        sr = client.get(
            ODDS_API_BASE + f"/events/{event_id}/odds/snapshot",
            headers=headers,
            params={
                "bookmakers": "pinnacle",
                "types": "total",
                "periods": "full time",
                "include_source": "true",
                "include_unavailable": "true",
            },
            timeout=(10, 30),
        )
        calls += 1
        captured_at = datetime.now(timezone.utc).replace(microsecond=0)
        try:
            sp = sr.json()
        except Exception:
            sp = {}
        base["odds_api_event_id"] = event_id
        if sr.status_code >= 300 or not isinstance(sp, Mapping):
            base["status"] = "BLOCKED_PROVIDER"
            rows.append(base)
            continue
        parsed = _extract_total_25(sp)
        if parsed is None:
            base["status"] = "BLOCKED_MARKET_INCOMPLETE"
            rows.append(base)
            continue
        over, under, provider_update = parsed
        age = int((captured_at - provider_update).total_seconds())
        base.update({
            "provider_quote_updated_at_utc": provider_update.isoformat(),
            "provider_quote_age_seconds": age,
            "over_2_5_decimal_odds": over,
            "under_2_5_decimal_odds": under,
            "fresh_120s": 0 <= age <= STRICT_FRESH_SECONDS,
            "status": "PASS_FRESH" if 0 <= age <= STRICT_FRESH_SECONDS else "BLOCKED_STALE",
        })
        rows.append(base)

    fresh = sum(1 for row in rows if row["fresh_120s"])
    matched = sum(1 for row in rows if row["odds_api_event_id"])
    payload = {
        "schema": "MATRIX_FOOTBALL_SHARP_ODDS_API_NET_PROBE_V1",
        "captured_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source_canonical_bundle_sha256": manifest.get("bundle_sha256"),
        "canonical_ready_input_count": manifest.get("ready_input_count"),
        "api_football_pinnacle_covered_fixture_count": len(covered_fixture_ids),
        "sample_selection": "EARLIEST_FUTURE_INTERSECTION_OF_CANONICAL_READY_AND_API_FOOTBALL_PINNACLE_COVERAGE",
        "sample_size": len(sample),
        "network_calls": calls,
        "identity_matched_count": matched,
        "strict_fresh_120s_count": fresh,
        "strict_fresh_120s_rate": (fresh / len(sample)) if sample else None,
        "reference_bookmaker": "Pinnacle",
        "transport": "odds-api.net",
        "market_scope": "FULL_TIME_TOTAL_2_5",
        "rows": rows,
        "protections": {
            "strict_fresh_gate_seconds": STRICT_FRESH_SECONDS,
            "odds_used_to_generate_probability": False,
            "p_matrix_status": "NOT_GENERATED",
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
        "status": "PASS" if rows else "NO_SAMPLE",
    }
    out=Path("evidence/api_football/sharp_odds_api_net_probe")
    out.mkdir(parents=True, exist_ok=True)
    (out/"manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)+"\n", encoding="utf-8")
    return payload


def main() -> None:
    result=run(api_key=os.environ.get("ODDS_API_NET_KEY", ""))
    print(json.dumps({
        "sample_size": result["sample_size"],
        "network_calls": result["network_calls"],
        "identity_matched_count": result["identity_matched_count"],
        "strict_fresh_120s_count": result["strict_fresh_120s_count"],
        "strict_fresh_120s_rate": result["strict_fresh_120s_rate"],
        "real_money": result["protections"]["real_money"],
        "status": result["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
