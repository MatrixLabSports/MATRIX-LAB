from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

import requests

BASE_URL = "https://v3.football.api-sports.io"
TARGET_BETS = {220: "Shots. Away Total", 221: "Shots. Home Total"}
POLICY_REFERENCE_BOOKMAKERS = {"betano", "bwin", "pinnacle"}
TIMEOUT_SECONDS = 20.0


def _utc(v: object) -> datetime:
    dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def candidates(now: datetime, minutes: int = 90, limit: int = 6) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for p in sorted(Path("evidence/api_football/prospective_daily").glob("*/*/fixtures/future_fixture_registry.json")):
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        captured = str(obj.get("captured_at_utc") or "")
        for e in obj.get("events") or []:
            if not isinstance(e, Mapping):
                continue
            fid = str(e.get("provider_fixture_id") or "")
            start = e.get("event_start_utc")
            if not fid or not start:
                continue
            kickoff = _utc(start)
            if not (now < kickoff <= now + timedelta(minutes=minutes)):
                continue
            row = dict(e)
            row["_captured"] = captured
            old = by_id.get(fid)
            if old is None or str(old.get("_captured") or "") < captured:
                by_id[fid] = row
    return sorted(by_id.values(), key=lambda x: (_utc(x["event_start_utc"]), int(x["provider_fixture_id"])))[:limit]


def extract_hits(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    hits = []
    for fixture_row in payload.get("response") or []:
        if not isinstance(fixture_row, Mapping):
            continue
        for book in fixture_row.get("bookmakers") or []:
            if not isinstance(book, Mapping):
                continue
            book_name = str(book.get("name") or "")
            for bet in book.get("bets") or []:
                if not isinstance(bet, Mapping):
                    continue
                try:
                    bet_id = int(bet.get("id"))
                except (TypeError, ValueError):
                    continue
                if bet_id not in TARGET_BETS:
                    continue
                values = []
                for val in bet.get("values") or []:
                    if not isinstance(val, Mapping):
                        continue
                    values.append({
                        "value": val.get("value"),
                        "odd": val.get("odd"),
                        "handicap": val.get("handicap"),
                        "main": val.get("main"),
                        "suspended": val.get("suspended"),
                    })
                hits.append({
                    "bookmaker_id": book.get("id"),
                    "bookmaker_name": book_name,
                    "policy_reference_bookmaker": book_name.strip().casefold() in POLICY_REFERENCE_BOOKMAKERS,
                    "bet_id": bet_id,
                    "bet_name": bet.get("name"),
                    "expected_catalog_name": TARGET_BETS[bet_id],
                    "values": values,
                })
    return hits


def run(api_key: str, out_root: Path) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    events = candidates(now)
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    run_dir = out_root / "runs" / run_id
    raw_dir = run_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    rows = []
    for e in events:
        fid = str(e["provider_fixture_id"])
        observed = datetime.now(timezone.utc).replace(microsecond=0)
        resp = session.get(
            BASE_URL + "/odds",
            headers={"x-apisports-key": key},
            params={"fixture": fid},
            timeout=TIMEOUT_SECONDS,
        )
        body = bytes(resp.content)
        path = raw_dir / f"fixture_{fid}_odds.bin"
        path.write_bytes(body)
        try:
            payload = resp.json()
        except ValueError:
            payload = {}
        errors = payload.get("errors") if isinstance(payload, Mapping) else None
        ok = 200 <= int(resp.status_code) < 300 and errors in ({}, [], None)
        hits = extract_hits(payload) if ok and isinstance(payload, Mapping) else []
        kickoff = _utc(e["event_start_utc"])
        rows.append({
            "fixture_id": fid,
            "home_team": e.get("home_team"),
            "away_team": e.get("away_team"),
            "kickoff_utc": kickoff.isoformat(),
            "observed_at_utc": observed.isoformat(),
            "observation_pre_kickoff": observed < kickoff,
            "minutes_before_kickoff": (kickoff - observed).total_seconds() / 60.0,
            "http_status": int(resp.status_code),
            "provider_ok": ok,
            "provider_errors": errors,
            "raw_path": str(path),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "canonical_target_hits": hits,
        })

    hits = [h for row in rows if row["observation_pre_kickoff"] for h in row["canonical_target_hits"]]
    policy_hits = [h for h in hits if h["policy_reference_bookmaker"]]
    if policy_hits:
        status = "PASS_CANONICAL_LIVE_PRICE_OBSERVED_POLICY_BOOKMAKER"
    elif hits:
        status = "PASS_CANONICAL_LIVE_PRICE_OBSERVED_OTHER_BOOKMAKER"
    else:
        status = "PASS_NO_CANONICAL_LIVE_PRICE_OBSERVED"

    manifest = {
        "schema": "MATRIX_TEAM_TOTAL_SHOTS_PREMATCH_ODDS_PROBE_V1",
        "run_id": run_id,
        "observed_at_utc": now.isoformat(),
        "provider": "api_football",
        "endpoint": "/odds",
        "target_bets": TARGET_BETS,
        "candidate_count": len(events),
        "network_calls": len(rows),
        "fixtures": rows,
        "canonical_live_hit_count": len(hits),
        "policy_reference_live_hit_count": len(policy_hits),
        "catalog_binding_resolved": True,
        "live_prematch_price_observed": bool(hits),
        "policy_reference_live_price_observed": bool(policy_hits),
        "prospective_freeze_started": False,
        "gates_started": False,
        "odds_used_to_generate_probability": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
        "status": status,
    }
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    pointer = {
        "schema": "MATRIX_TEAM_TOTAL_SHOTS_PREMATCH_ODDS_PROBE_POINTER_V1",
        "run_id": run_id,
        "manifest_path": str(manifest_path),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "status": status,
        "canonical_live_hit_count": len(hits),
        "policy_reference_live_hit_count": len(policy_hits),
        "live_prematch_price_observed": bool(hits),
        "policy_reference_live_price_observed": bool(policy_hits),
        "prospective_freeze_started": False,
        "gates_started": False,
        "real_money": "BLOCKED",
    }
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "last_run.json").write_text(json.dumps(pointer, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    result = run(
        os.environ.get("API_FOOTBALL_KEY", ""),
        Path("evidence/api_football/market_expansion/team_total_shots_odds_probe"),
    )
    print(json.dumps({
        "status": result["status"],
        "candidate_count": result["candidate_count"],
        "network_calls": result["network_calls"],
        "canonical_live_hit_count": result["canonical_live_hit_count"],
        "policy_reference_live_hit_count": result["policy_reference_live_hit_count"],
        "prospective_freeze_started": result["prospective_freeze_started"],
        "real_money": result["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
