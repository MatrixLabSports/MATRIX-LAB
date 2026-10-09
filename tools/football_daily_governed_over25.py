from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle
from tools.api_football_market_shadow_p_matrix import build_shadow_p_matrix

POLICY = {
    "betano": ["betano"],
    "betplay": ["betplay"],
    "bwin": ["bwin"],
    "rushbet": ["rushbet", "rush bet"],
}
DIAGNOSTIC = {"pinnacle": ["pinnacle"]}


def norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def match_book(name: str, mapping: dict[str, list[str]]) -> str | None:
    n = norm(name)
    for key, tokens in mapping.items():
        if any(norm(token) in n for token in tokens):
            return key
    return None


def odd(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    return x if x > 1.0 else None


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def latest_cycle(root: Path, target_date: str) -> Path:
    base = root / "evidence" / "api_football" / "prospective_daily" / target_date
    candidates = sorted(p for p in base.glob("*") if p.is_dir() and (p / "cycle_summary.json").exists())
    if not candidates:
        raise SystemExit(f"NO_PROSPECTIVE_CYCLE:{target_date}")
    valid = []
    for p in candidates:
        try:
            j = json.loads((p / "cycle_summary.json").read_text(encoding="utf-8"))
        except Exception:
            continue
        if j.get("status") == "PASS" and j.get("target_date_bogota") == target_date:
            valid.append(p)
    if not valid:
        raise SystemExit(f"NO_VALID_PROSPECTIVE_CYCLE:{target_date}")
    return valid[-1]


def dedupe(xs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, float]] = set()
    out: list[dict[str, Any]] = []
    for x in xs:
        key = (str(x["house_key"]), float(x["decimal_odds"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def build(target_date: str, api_key: str, root: Path = Path(".")) -> dict[str, Any]:
    api_key = str(api_key or "").strip()
    if not api_key:
        raise SystemExit("API_FOOTBALL_KEY_NOT_CONFIGURED")
    api_key.encode("ascii")

    cycle = latest_cycle(root, target_date)
    canonical, manifest = load_chunked_canonical_bundle(cycle / "canonical_analysis")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    p_matrix = build_shadow_p_matrix(
        canonical_bundle=canonical,
        canonical_manifest=manifest,
        raw_dir=cycle / "history" / "raw",
        generated_at=generated_at,
    )

    report_root = root / "evidence" / "api_football" / "daily_prematch_reports" / target_date
    report_root.mkdir(parents=True, exist_ok=True)
    p_path = report_root / "p_matrix_shadow_current.json"
    p_path.write_text(
        json.dumps(p_matrix, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    ev_root = report_root / "over25_shadow_ev"
    raw_root = ev_root / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    client = requests.Session()
    rows: list[dict[str, Any]] = []
    calls = 0

    for row in p_matrix.get("rows", []):
        fixture_id = str(row["fixture_id"])
        kickoff = parse_utc(row["kickoff_utc"])
        probability = float(row["p_matrix_shadow"]["over_2_5"])
        match = f'{row.get("home_team")} vs {row.get("away_team")}'

        if kickoff <= now:
            rows.append({
                "fixture_id": fixture_id,
                "match": match,
                "kickoff_utc": row["kickoff_utc"],
                "p_over_2_5": probability,
                "decision": "BLOCKED",
                "reason": "EVENT_NOT_FUTURE_AT_ODDS_QUERY",
                "policy_offers": [],
                "diagnostic_offers": [],
                "best_policy_offer": None,
            })
            continue

        response = client.get(
            "https://v3.football.api-sports.io/odds",
            headers={"x-apisports-key": api_key},
            params={"fixture": fixture_id},
            timeout=(10, 30),
        )
        calls += 1
        body = bytes(response.content)
        (raw_root / f"fixture_{fixture_id}.bin").write_bytes(body)
        try:
            payload = response.json()
        except Exception:
            payload = {}
        errors = payload.get("errors") if isinstance(payload, dict) else None
        policy_offers: list[dict[str, Any]] = []
        diagnostic_offers: list[dict[str, Any]] = []

        if 200 <= response.status_code < 300 and errors in ({}, [], None):
            for fixture_row in payload.get("response", []) or []:
                if not isinstance(fixture_row, dict):
                    continue
                for bookmaker in fixture_row.get("bookmakers", []) or []:
                    if not isinstance(bookmaker, dict):
                        continue
                    bookmaker_name = str(bookmaker.get("name") or "")
                    policy_key = match_book(bookmaker_name, POLICY)
                    diagnostic_key = match_book(bookmaker_name, DIAGNOSTIC)
                    if not policy_key and not diagnostic_key:
                        continue
                    for bet in bookmaker.get("bets", []) or []:
                        if not isinstance(bet, dict):
                            continue
                        try:
                            bet_id = int(bet.get("id"))
                        except Exception:
                            continue
                        bet_name = str(bet.get("name") or "").strip()
                        if bet_id != 5 or bet_name.casefold() != "goals over/under":
                            continue
                        for value in bet.get("values", []) or []:
                            if not isinstance(value, dict):
                                continue
                            if str(value.get("value") or "").strip().casefold() != "over 2.5":
                                continue
                            decimal = odd(value.get("odd"))
                            if decimal is None:
                                continue
                            offer = {
                                "house_key": policy_key or diagnostic_key,
                                "bookmaker_id": bookmaker.get("id"),
                                "bookmaker_name": bookmaker_name,
                                "bet_id": bet_id,
                                "bet_name": bet_name,
                                "label": "Over 2.5",
                                "decimal_odds": decimal,
                                "break_even_probability": 1.0 / decimal,
                                "p_matrix": probability,
                                "ev": probability * decimal - 1.0,
                                "odds_used_to_generate_probability": False,
                            }
                            (policy_offers if policy_key else diagnostic_offers).append(offer)

        policy_offers = dedupe(policy_offers)
        diagnostic_offers = dedupe(diagnostic_offers)
        eligible = [x for x in policy_offers if float(x["decimal_odds"]) > 1.50]
        best = max(eligible, key=lambda x: float(x["ev"])) if eligible else None

        if best is None:
            decision = "BLOCKED"
            reason = "NO_EXACT_POLICY_HOUSE_OVER25_ODDS_ABOVE_1_50"
        elif float(best["ev"]) > 0:
            decision = "BET_SHADOW"
            reason = "EXACT_POLICY_HOUSE_ODDS_AND_POSITIVE_EV"
        else:
            decision = "NO_BET"
            reason = "EXACT_POLICY_HOUSE_ODDS_BUT_EV_NOT_POSITIVE"

        rows.append({
            "fixture_id": fixture_id,
            "match": match,
            "league_id": row.get("league_id"),
            "kickoff_utc": row["kickoff_utc"],
            "p_over_2_5": probability,
            "fair_decimal_odds": 1.0 / probability,
            "policy_offers": policy_offers,
            "diagnostic_offers": diagnostic_offers,
            "best_policy_offer": best,
            "decision": decision,
            "reason": reason,
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "provider_http_status": int(response.status_code),
            "provider_errors": errors,
        })

    for blocked in p_matrix.get("blocked", []):
        rows.append({
            "fixture_id": str(blocked.get("fixture_id") or ""),
            "match": None,
            "kickoff_utc": None,
            "p_over_2_5": None,
            "policy_offers": [],
            "diagnostic_offers": [],
            "best_policy_offer": None,
            "decision": "BLOCKED",
            "reason": "P_MATRIX_BLOCKED:" + str(blocked.get("reason")),
        })

    order = {"BET_SHADOW": 0, "NO_BET": 1, "BLOCKED": 2}
    rows.sort(
        key=lambda x: (
            order.get(str(x["decision"]), 9),
            -float((x.get("best_policy_offer") or {}).get("ev", -999)),
            str(x.get("kickoff_utc") or ""),
            str(x.get("fixture_id") or ""),
        )
    )
    bets = [x for x in rows if x["decision"] == "BET_SHADOW"]
    no_bets = [x for x in rows if x["decision"] == "NO_BET"]
    blocked_rows = [x for x in rows if x["decision"] == "BLOCKED"]

    output = {
        "schema": "MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV_V2",
        "generated_at_utc": now.isoformat(),
        "target_date_bogota": target_date,
        "source_cycle": cycle.as_posix(),
        "market": "OVER_2_5",
        "probability_engine": "calibrated_log_pool_v1",
        "probability_status": "FROZEN_SHADOW_RESEARCH",
        "market_governance_status": "STRONG_PROMOTED_SIGNAL_ENGINE",
        "exact_market_binding": {"bet_id": 5, "bet_name": "Goals Over/Under", "value": "Over 2.5"},
        "policy_houses": ["Betano", "BetPlay", "bwin", "RushBet"],
        "diagnostic_only": ["Pinnacle"],
        "minimum_decimal_odds_exclusive": 1.50,
        "ev_formula": "P_MATRIX * DECIMAL_ODDS - 1",
        "bet_shadow_requires_positive_ev": True,
        "network_calls": calls,
        "p_matrix_scored_count": int(p_matrix["scored_count"]),
        "p_matrix_blocked_count": int(p_matrix["blocked_count"]),
        "decision_counts": {
            "BET_SHADOW": len(bets),
            "NO_BET": len(no_bets),
            "BLOCKED": len(blocked_rows),
        },
        "bet_shadow": bets,
        "no_bet": no_bets,
        "blocked": blocked_rows,
        "all_rows": rows,
        "protections": {
            "probability_frozen_before_odds_query": True,
            "odds_used_to_generate_probability": False,
            "target_outcomes_used": False,
            "broad_market_matching_forbidden": True,
            "pinnacle_not_executable_house": True,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }
    blob = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    output["sha256_without_self"] = hashlib.sha256(blob).hexdigest()

    out_path = ev_root / "MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV.json"
    out_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    summary = {
        "target_date_bogota": target_date,
        "cycle_root": cycle.as_posix(),
        "ready_inputs": int(p_matrix["source_ready_input_count"]),
        "p_matrix_scored": int(p_matrix["scored_count"]),
        "p_matrix_blocked": int(p_matrix["blocked_count"]),
        "network_calls": calls,
        "decision_counts": output["decision_counts"],
        "top_shadow": [
            {
                "fixture_id": x["fixture_id"],
                "match": x["match"],
                "p": x["p_over_2_5"],
                "house": x["best_policy_offer"]["bookmaker_name"],
                "odds": x["best_policy_offer"]["decimal_odds"],
                "ev": x["best_policy_offer"]["ev"],
            }
            for x in bets[:15]
        ],
        "real_money": "BLOCKED",
    }
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", required=True)
    args = parser.parse_args()
    result = build(args.target_date, os.environ.get("API_FOOTBALL_KEY", ""))
    assert result["protections"]["probability_frozen_before_odds_query"] is True
    assert result["protections"]["odds_used_to_generate_probability"] is False
    assert result["protections"]["automatic_wagering"] is False
    assert result["protections"]["real_money"] == "BLOCKED"
    for row in result["bet_shadow"]:
        best = row["best_policy_offer"]
        assert best["decimal_odds"] > 1.50
        assert best["ev"] > 0
        assert best["bet_id"] == 5
        assert best["bet_name"] == "Goals Over/Under"
        assert best["label"] == "Over 2.5"
        assert best["house_key"] in {"betano", "betplay", "bwin", "rushbet"}


if __name__ == "__main__":
    main()
