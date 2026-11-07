"""Independent, fail-closed football-data.org fixture intake for MATRIX.

This module NEVER supplies probabilities, prices, or betting signals. It keeps
provider identities separate from API-Football identities and never rewrites
the calibrated model or its historical inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
ENDPOINT = "https://api.football-data.org/v4/matches"
SCHEMA = "MATRIX_INDEPENDENT_FIXTURE_INTAKE_V1"
SOURCE_ORDER = ["SOFASCORE", "FLASHSCORE", "APIS"]
MAX_BYTES = 3_000_000
VALID_PREMATCH = {"SCHEDULED", "TIMED"}

def normalize(response: dict, target_day: str, now_utc: datetime) -> list[dict]:
    """Admit distinct, genuinely prospective fixtures in the Bogota day only."""
    date.fromisoformat(target_day)
    if not isinstance(response, dict) or not isinstance(response.get("matches"), list):
        raise ValueError("MATCHES_ARRAY_REQUIRED")
    output, seen = [], set()
    for raw in response["matches"]:
        if not isinstance(raw, dict) or raw.get("status") not in VALID_PREMATCH:
            continue
        home, away = raw.get("homeTeam"), raw.get("awayTeam")
        if not isinstance(home, dict) or not isinstance(away, dict):
            continue
        try:
            fid = str(int(raw["id"]))
            home_id, away_id = str(int(home["id"])), str(int(away["id"]))
            kickoff = datetime.fromisoformat(str(raw["utcDate"]).replace("Z", "+00:00"))
            if kickoff.tzinfo is None:
                continue
            kickoff = kickoff.astimezone(timezone.utc)
        except (KeyError, ValueError, TypeError, OverflowError):
            continue
        if kickoff <= now_utc or kickoff.astimezone(BOGOTA).date().isoformat() != target_day:
            continue
        if fid in seen or home_id == away_id:
            raise ValueError("DUPLICATE_OR_INVALID_PROVIDER_FIXTURE_ID")
        seen.add(fid)
        home_name = str(home.get("name") or "").strip()
        away_name = str(away.get("name") or "").strip()
        if not home_name or not away_name:
            continue
        output.append({
            "source": "FOOTBALL_DATA_ORG",
            "source_fixture_id": fid,
            "home": home_name,
            "away": away_name,
            "home_source_team_id": home_id,
            "away_source_team_id": away_id,
            "kickoff_utc": kickoff.isoformat(),
            "league": str((raw.get("competition") or {}).get("name") or ""),
            "source_competition_id": (raw.get("competition") or {}).get("id"),
            "source_competition_code": (raw.get("competition") or {}).get("code"),
            "source_status": raw["status"],
            "api_football_fixture_id": None,
            "browser_identity_verified": False,
            "provider_identity_crosswalk_verified": False,
            "historical_features_verified": False,
            "exact_quote_verified": False,
            "signal_generation_authorized": False,
        })
    return sorted(output, key=lambda x: (x["kickoff_utc"], x["source_fixture_id"]))

def capture(target_day: str, token: str, *, opener=urlopen, now_utc: datetime | None = None) -> dict:
    """One authenticated network call with bounded read, auditable metadata and safe errors."""
    day = date.fromisoformat(target_day)
    now = now_utc or datetime.now(timezone.utc)
    result = {
        "schema": SCHEMA,
        "target_date_bogota": target_day,
        "generated_at_utc": now.astimezone(timezone.utc).isoformat(),
        "source": "FOOTBALL_DATA_ORG",
        "source_order": SOURCE_ORDER,
        "status": "DISCOVERY_ONLY_NO_GOVERNED_PROBABILITY_OR_QUOTES",
        "provider_status": "BLOCKED",
        "provider_calls": 0,
        "fixtures": [],
        "fixture_count": 0,
        "worldwide_complete": False,
        "browser_first_preregistration_verified": False,
        "cross_provider_identity_verified": False,
        "governed_feature_equivalence_verified": False,
        "exact_bookmaker_odds_verified": False,
        "signal_generation_authorized": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    if not token.strip():
        result["provider_status"] = "MISSING_FOOTBALL_DATA_ORG_TOKEN"
        return result
    params = {"dateFrom": day.isoformat(), "dateTo": (day + timedelta(days=1)).isoformat()}
    url = ENDPOINT + "?" + urlencode(params)
    request = Request(url, headers={"X-Auth-Token": token, "Accept": "application/json"})
    result["provider_calls"] = 1
    result["request_scope"] = params
    try:
        with opener(request, timeout=25) as response:
            result["http_status"] = int(response.status)
            body = response.read(MAX_BYTES + 1)
        result["response_bytes"] = len(body)
        result["response_sha256"] = hashlib.sha256(body).hexdigest()
        if len(body) > MAX_BYTES:
            result["provider_status"] = "RESPONSE_TOO_LARGE"
            return result
        payload = json.loads(body.decode("utf-8"))
        if result["http_status"] != 200:
            result["provider_status"] = "NON_200_RESPONSE"
            return result
        fixtures = normalize(payload, target_day, now)
        result["fixtures"] = fixtures
        result["fixture_count"] = len(fixtures)
        result["provider_status"] = "AUTHENTICATED_FIXTURE_CAPTURE" if fixtures else "AUTHENTICATED_NO_FUTURE_FIXTURES_IN_SCOPE"
    except HTTPError as exc:
        result["http_status"] = int(exc.code)
        result["provider_status"] = "PROVIDER_HTTP_ERROR"
    except (URLError, TimeoutError, OSError) as exc:
        result["provider_status"] = "NETWORK_ERROR"
        result["error_type"] = type(exc).__name__
    except (ValueError, UnicodeError, TypeError, KeyError) as exc:
        result["provider_status"] = "INVALID_PROVIDER_RESPONSE"
        result["error_type"] = type(exc).__name__
    return result

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--scores", type=Path, default=None, help="Optional, separately certified governed score export")
    parser.add_argument("--promotion", type=Path, default=Path("evidence/api_football/governance/over_2_5_p_matrix_promotion.json"))
    args = parser.parse_args()
    result = capture(args.date, os.environ.get("FOOTBALL_DATA_ORG_TOKEN", ""))
    if args.scores is not None and args.scores.is_file():
        from tools.matrix_independent_over25_governed_binding import bind
        scores = json.loads(args.scores.read_text(encoding="utf-8"))
        promotion = json.loads(args.promotion.read_text(encoding="utf-8"))
        bound = bind(result, scores, promotion)
        result["governed_score_binding"] = {
            "bound_rows": len(bound["rows"]),
            "rejected_rows": len(bound["rejected"]),
            "signal_generation_authorized": False,
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in (
        "target_date_bogota", "provider_status", "fixture_count",
        "signal_generation_authorized", "real_money"
    )}, sort_keys=True))

if __name__ == "__main__":
    main()
