from __future__ import annotations

import hashlib
import json
import math
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Mapping

import requests

from app.research.football.prospective_ledger import (
    ClosingOddsReference,
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
)
from matrix_elite.market_history import market_snapshot_sha256
from matrix_elite.odds import OddsSnapshot, fair_market_probabilities
from tools.football_clv_tracking_cycle import (
    CLOSE_WINDOW_MINUTES,
    DEFAULT_ATTEMPT_LOG,
    DEFAULT_CAPTURE_DIR,
    DEFAULT_LEDGER,
    MARKET_KEY,
    MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
    MODEL_VERSION,
    PINNACLE_BOOKMAKER_NAME,
    SELECTION_KEY,
    _append_closing_attempt,
    _aware,
    _canonical_sha256,
)

API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
ODDS_API_BASE = "https://api.odds-api.net/v1"


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _sim(left: Any, right: Any) -> float:
    a, b = _norm(left), _norm(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, a, b).ratio()
    subset = 1.0 if ta <= tb or tb <= ta else 0.0
    return max(jac, seq, subset)


def _existing(
    ledger: FootballProspectiveEvidenceLedger,
) -> tuple[list[FrozenProspectiveDecision], set[str]]:
    decisions: list[FrozenProspectiveDecision] = []
    closed: set[str] = set()
    for event in ledger.load_events():
        if event.event_type == "DECISION_FROZEN":
            decisions.append(FrozenProspectiveDecision.from_mapping(event.payload))
        elif event.event_type == "CLOSING_ODDS_RECORDED":
            closed.add(ClosingOddsReference.from_mapping(event.payload).decision_id)
    return decisions, closed


def _get_json(session: Any, url: str, *, headers: Mapping[str, str], params: Mapping[str, Any] | None = None):
    response = session.get(url, headers=dict(headers), params=dict(params or {}), timeout=(10, 30))
    try:
        payload = response.json()
    except Exception:
        payload = {}
    return response, payload


def _exact_line_from_item(item: Mapping[str, Any]) -> float | None:
    raw = item.get("line")
    try:
        if raw is not None and not isinstance(raw, bool):
            return float(raw)
    except (TypeError, ValueError):
        pass
    # Current odds-api.net contract may encode the side together with the line,
    # e.g. line="over 2.5" / "under 2.5". Accept only that exact form.
    raw_text = str(raw or "").strip()
    m = re.fullmatch(r"(?i)\s*(?:over|under)\s+([0-9]+(?:\.[0-9]+)?)\s*", raw_text)
    if m:
        return float(m.group(1))
    # Strict secondary fallback for older/alternate payloads where the exact
    # total is in selection_name.
    label = str(item.get("selection_name") or "").strip()
    m = re.fullmatch(r"(?i)\s*(?:over|under)\s+([0-9]+(?:\.[0-9]+)?)\s*", label)
    return float(m.group(1)) if m else None


def _is_standard_goal_total(item: Mapping[str, Any]) -> bool:
    metric = _norm(item.get("metric"))
    if metric and metric != "standard":
        return False
    market_text = " ".join([_norm(item.get("market_key")), _norm(item.get("bet_type"))])
    return "total" in market_text or "over under" in market_text


def _extract_total_25(snapshot: Mapping[str, Any]) -> tuple[float, float, datetime] | None:
    ts_ms = (snapshot.get("bookmaker_as_of_ts_ms") or {}).get("pinnacle")
    if not isinstance(ts_ms, (int, float)):
        return None
    provider_update = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
    over = under = None
    for item in snapshot.get("items") or []:
        if not isinstance(item, Mapping):
            continue
        if _norm(item.get("bookmaker")) != "pinnacle":
            continue
        try:
            line = _exact_line_from_item(item)
            odds = float(item.get("odds"))
            if line is None:
                raise ValueError("LINE_MISSING")
        except (TypeError, ValueError):
            continue
        if line != 2.5 or odds <= 1.0 or item.get("is_available") is False:
            continue
        if not _is_standard_goal_total(item):
            continue
        label = " ".join([
            _norm(item.get("side")),
            _norm(item.get("selection_name")),
        ])
        if "over" in label:
            over = odds
        elif "under" in label:
            under = odds
    if over is None or under is None:
        return None
    return over, under, provider_update



def _diagnose_total_25(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    ts_ms = (snapshot.get("bookmaker_as_of_ts_ms") or {}).get("pinnacle")
    diagnostic: dict[str, Any] = {
        "market_diagnostic_version": 2,
        "provider_timestamp_present": isinstance(ts_ms, (int, float)),
        "pinnacle_item_count": 0,
        "total_market_item_count": 0,
        "available_total_lines": [],
        "sample_total_items": [],
        "over_2_5_present": False,
        "under_2_5_present": False,
        "incomplete_reason": None,
    }
    lines: set[float] = set()
    for item in snapshot.get("items") or []:
        if not isinstance(item, Mapping) or _norm(item.get("bookmaker")) != "pinnacle":
            continue
        diagnostic["pinnacle_item_count"] += 1
        if not _is_standard_goal_total(item):
            continue
        diagnostic["total_market_item_count"] += 1
        if len(diagnostic["sample_total_items"]) < 12:
            diagnostic["sample_total_items"].append({
                "market_key": item.get("market_key"),
                "bet_type": item.get("bet_type"),
                "metric": item.get("metric"),
                "period": item.get("period"),
                "period_str": item.get("period_str"),
                "line": item.get("line"),
                "side": item.get("side"),
                "selection_name": item.get("selection_name"),
                "odds": item.get("odds"),
                "is_available": item.get("is_available"),
            })
        try:
            line = _exact_line_from_item(item)
            odds = float(item.get("odds"))
            if line is None:
                raise ValueError("LINE_MISSING")
        except (TypeError, ValueError):
            continue
        if item.get("is_available") is False or odds <= 1.0:
            continue
        lines.add(line)
        if line != 2.5:
            continue
        label = " ".join([
            _norm(item.get("side")),
            _norm(item.get("selection_name")),
        ])
        if "over" in label:
            diagnostic["over_2_5_present"] = True
        elif "under" in label:
            diagnostic["under_2_5_present"] = True
    diagnostic["available_total_lines"] = sorted(lines)
    if not diagnostic["provider_timestamp_present"]:
        reason = "PROVIDER_TIMESTAMP_MISSING"
    elif diagnostic["pinnacle_item_count"] == 0:
        reason = "PINNACLE_ITEMS_MISSING"
    elif diagnostic["total_market_item_count"] == 0:
        reason = "TOTAL_MARKET_MISSING"
    elif 2.5 not in diagnostic["available_total_lines"]:
        reason = "TOTAL_2_5_LINE_MISSING"
    elif not diagnostic["over_2_5_present"]:
        reason = "OVER_2_5_MISSING"
    elif not diagnostic["under_2_5_present"]:
        reason = "UNDER_2_5_MISSING"
    else:
        reason = "COMPLETE"
    diagnostic["incomplete_reason"] = reason
    return diagnostic


def capture_due_via_odds_api_net(
    *,
    ledger_path: Path = DEFAULT_LEDGER,
    capture_dir: Path = DEFAULT_CAPTURE_DIR,
    attempt_log_path: Path = DEFAULT_ATTEMPT_LOG,
    api_football_key: str,
    odds_api_key: str,
    now: datetime | None = None,
    session: Any | None = None,
    capture_clock: Any | None = None,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    clock = capture_clock or (lambda: datetime.now(timezone.utc))
    ledger = FootballProspectiveEvidenceLedger(ledger_path)
    decisions, closed = _existing(ledger)
    due: list[FrozenProspectiveDecision] = []
    for decision in decisions:
        if decision.decision_id in closed:
            continue
        kickoff = _aware(decision.fixture_kickoff_utc, name="KICKOFF")
        lead = kickoff - reference
        if 0 < lead.total_seconds() <= CLOSE_WINDOW_MINUTES * 60:
            due.append(decision)

    result = {
        "transport": "odds-api.net",
        "due_count": len(due),
        "network_calls": 0,
        "captured_new": 0,
        "blocked_credential": 0,
        "blocked_fixture_lookup": 0,
        "blocked_identity": 0,
        "blocked_market_incomplete": 0,
        "blocked_stale_provider_quote": 0,
        "blocked_temporal": 0,
        "blocked_provider_error": 0,
        "evidence_paths": [],
        "real_money": "BLOCKED",
    }
    if not due:
        return result
    if not str(odds_api_key or "").strip():
        result["blocked_credential"] = len(due)
        return result
    if not str(api_football_key or "").strip():
        result["blocked_fixture_lookup"] = len(due)
        return result

    client = session or requests.Session()
    af_headers = {"x-apisports-key": str(api_football_key).strip()}
    oa_headers = {"X-API-Key": str(odds_api_key).strip(), "Accept": "application/json"}
    capture_dir.mkdir(parents=True, exist_ok=True)

    for decision in sorted(due, key=lambda d: (d.fixture_kickoff_utc, d.fixture_id)):
        kickoff = _aware(decision.fixture_kickoff_utc, name="KICKOFF")
        base = {
            "schema": "MATRIX_FOOTBALL_CLV_CLOSING_ATTEMPT_V1",
            "decision_id": decision.decision_id,
            "fixture_id": decision.fixture_id,
            "market_key": decision.market_key,
            "selection_key": decision.selection_key,
            "transport": "odds-api.net /v1/events/{event_id}/odds/snapshot",
            "reference_bookmaker": PINNACLE_BOOKMAKER_NAME,
            "fixture_kickoff_utc": kickoff.isoformat(),
            "strict_fresh_gate_seconds": MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        }

        fr, fp = _get_json(
            client,
            API_FOOTBALL_BASE + "/fixtures",
            headers=af_headers,
            params={"id": decision.fixture_id},
        )
        result["network_calls"] += 1
        lookup_attempted_raw = clock()
        if lookup_attempted_raw.tzinfo is None or lookup_attempted_raw.utcoffset() is None:
            raise ValueError("CAPTURE_CLOCK_MUST_BE_TIMEZONE_AWARE")
        lookup_attempted_at = lookup_attempted_raw.astimezone(timezone.utc).replace(microsecond=0)
        rows = fp.get("response") if isinstance(fp, Mapping) else []
        if fr.status_code >= 300 or not rows:
            result["blocked_fixture_lookup"] += 1
            _append_closing_attempt(attempt_log_path, {
                **base,
                "attempted_at_utc": lookup_attempted_at.isoformat(),
                "capture_lead_seconds": int((kickoff-lookup_attempted_at).total_seconds()),
                "outcome": "ODDS_API_BLOCKED_FIXTURE_LOOKUP",
                "http_status": int(fr.status_code),
                "provider_quote_updated_at_utc": None,
                "provider_quote_age_seconds": None,
                "gate_excess_seconds": None,
            })
            continue

        row = rows[0]
        home = str((row.get("teams") or {}).get("home", {}).get("name") or "")
        away = str((row.get("teams") or {}).get("away", {}).get("name") or "")
        start = int(kickoff.timestamp())
        er, ep = _get_json(
            client,
            ODDS_API_BASE + "/events",
            headers=oa_headers,
            params={
                "sport": "soccer",
                "start_from": start - 900,
                "start_to": start + 900,
                "limit": 100,
                "include_bookmaker_ids": "true",
            },
        )
        result["network_calls"] += 1
        identity_attempted_raw = clock()
        if identity_attempted_raw.tzinfo is None or identity_attempted_raw.utcoffset() is None:
            raise ValueError("CAPTURE_CLOCK_MUST_BE_TIMEZONE_AWARE")
        identity_attempted_at = identity_attempted_raw.astimezone(timezone.utc).replace(microsecond=0)
        events = ep.get("items") if isinstance(ep, Mapping) else []
        scored: list[tuple[float, bool, Mapping[str, Any]]] = []
        for event in events or []:
            if not isinstance(event, Mapping):
                continue
            direct = (_sim(home, event.get("home_team")) + _sim(away, event.get("away_team"))) / 2.0
            swapped = (_sim(home, event.get("away_team")) + _sim(away, event.get("home_team"))) / 2.0
            scored.append((max(direct, swapped), direct >= swapped, event))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0] if scored else None
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        if (
            er.status_code >= 300
            or best is None
            or best[0] < 0.85
            or (len(scored) > 1 and best[0] - second_score < 0.05)
        ):
            result["blocked_identity"] += 1
            _append_closing_attempt(attempt_log_path, {
                **base,
                "attempted_at_utc": identity_attempted_at.isoformat(),
                "capture_lead_seconds": int((kickoff-identity_attempted_at).total_seconds()),
                "outcome": "ODDS_API_BLOCKED_IDENTITY",
                "http_status": int(er.status_code),
                "provider_quote_updated_at_utc": None,
                "provider_quote_age_seconds": None,
                "gate_excess_seconds": None,
                "best_identity_score": best[0] if best else None,
                "second_identity_score": second_score if best else None,
            })
            continue

        score, direct, event = best
        event_id = str(event.get("event_id") or "")
        sr, sp = _get_json(
            client,
            ODDS_API_BASE + f"/events/{event_id}/odds/snapshot",
            headers=oa_headers,
            params={
                "bookmakers": "pinnacle",
                "types": "total",
                "periods": "full time",
                "include_source": "true",
                "include_unavailable": "true",
            },
        )
        result["network_calls"] += 1
        captured_raw = clock()
        if captured_raw.tzinfo is None or captured_raw.utcoffset() is None:
            raise ValueError("CAPTURE_CLOCK_MUST_BE_TIMEZONE_AWARE")
        captured_at = captured_raw.astimezone(timezone.utc).replace(microsecond=0)
        attempt = {
            **base,
            "attempted_at_utc": captured_at.isoformat(),
            "capture_lead_seconds": int((kickoff-captured_at).total_seconds()),
            "http_status": int(sr.status_code),
            "odds_api_event_id": event_id,
            "identity_score": score,
            "identity_orientation": "direct" if direct else "swapped",
            "provider_quote_updated_at_utc": None,
            "provider_quote_age_seconds": None,
            "gate_excess_seconds": None,
        }
        if sr.status_code >= 300 or not isinstance(sp, Mapping):
            result["blocked_provider_error"] += 1
            _append_closing_attempt(attempt_log_path, {**attempt, "outcome": "ODDS_API_BLOCKED_PROVIDER_ERROR"})
            continue

        parsed = _extract_total_25(sp)
        if parsed is None:
            result["blocked_market_incomplete"] += 1
            market_diagnostic = _diagnose_total_25(sp)
            _append_closing_attempt(
                attempt_log_path,
                {
                    **attempt,
                    "outcome": "ODDS_API_BLOCKED_MARKET_INCOMPLETE",
                    "market_diagnostic": market_diagnostic,
                },
            )
            continue
        over_odds, under_odds, provider_update = parsed
        quote_age = int((captured_at-provider_update).total_seconds())
        gate_excess_seconds = max(
            0,
            quote_age - MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
        )
        attempt.update({
            "provider_quote_updated_at_utc": provider_update.isoformat(),
            "provider_quote_age_seconds": quote_age,
            "gate_excess_seconds": gate_excess_seconds,
            "over_2_5_decimal_odds": over_odds,
            "under_2_5_decimal_odds": under_odds,
        })
        if captured_at >= kickoff or provider_update >= kickoff or provider_update > captured_at:
            result["blocked_temporal"] += 1
            _append_closing_attempt(attempt_log_path, {**attempt, "outcome": "ODDS_API_BLOCKED_TEMPORAL"})
            continue
        if quote_age > MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS:
            result["blocked_stale_provider_quote"] += 1
            _append_closing_attempt(attempt_log_path, {**attempt, "outcome": "ODDS_API_BLOCKED_STALE_PROVIDER_QUOTE"})
            continue

        snapshots = (
            OddsSnapshot(
                event_id=decision.fixture_id,
                market_id="total_goals_2_5",
                selection_id="over_2_5",
                provider=PINNACLE_BOOKMAKER_NAME,
                captured_at=provider_update,
                decimal_odds=over_odds,
                is_live=False,
            ),
            OddsSnapshot(
                event_id=decision.fixture_id,
                market_id="total_goals_2_5",
                selection_id="under_2_5",
                provider=PINNACLE_BOOKMAKER_NAME,
                captured_at=provider_update,
                decimal_odds=under_odds,
                is_live=False,
            ),
        )
        fair = fair_market_probabilities(snapshots)
        fair_over = float(fair["over_2_5"])
        snapshot_sha = market_snapshot_sha256(snapshots)
        evidence = {
            "schema": "MATRIX_FOOTBALL_CLV_CLOSING_CAPTURE_V1",
            "decision_id": decision.decision_id,
            "fixture_id": decision.fixture_id,
            "market_key": decision.market_key,
            "selection_key": decision.selection_key,
            "model_version": decision.model_version,
            "entry": {
                "provider": decision.odds_source_provider,
                "decimal_odds": decision.decimal_odds,
                "observed_at_utc": decision.odds_observed_at_utc,
                "decision_at_utc": decision.decision_at_utc,
                "quote_sha256": decision.odds_snapshot_sha256,
            },
            "closing": {
                "provider": PINNACLE_BOOKMAKER_NAME,
                "transport": "odds-api.net",
                "direct_pinnacle_api_connection": False,
                "source_quality_flag": "SHARP_PINNACLE_VIA_ODDS_API_NET_STRICT_120S_AUTO",
                "system_captured_at_utc": captured_at.isoformat(),
                "provider_quote_updated_at_utc": provider_update.isoformat(),
                "provider_quote_age_seconds": quote_age,
                "gate_excess_seconds": gate_excess_seconds,
                "kickoff_utc": kickoff.isoformat(),
                "capture_lead_seconds": int((kickoff-captured_at).total_seconds()),
                "complete_market_snapshot": True,
                "over_2_5_decimal_odds": over_odds,
                "under_2_5_decimal_odds": under_odds,
                "fair_over_2_5_probability_devigged": fair_over,
                "devig_method": "MULTIPLICATIVE",
                "market_snapshot_sha256": snapshot_sha,
                "odds_api_event_id": event_id,
            },
            "clv": {
                "log_price_clv": math.log(decision.decimal_odds / over_odds),
                "probability_clv_vs_devigged_close": fair_over - (1.0 / decision.decimal_odds),
                "fair_odds_clv_ratio": decision.decimal_odds * fair_over - 1.0,
            },
            "protections": {
                "post_kickoff_close_forbidden": True,
                "incomplete_market_devig_forbidden": True,
                "provider_quote_age_bounded_seconds": MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS,
                "odds_used_to_generate_probability": False,
                "automatic_wagering": False,
                "real_money": "BLOCKED",
            },
        }
        evidence["payload_sha256"] = _canonical_sha256(evidence)
        safe_id = hashlib.sha256(decision.decision_id.encode("utf-8")).hexdigest()
        evidence_path = capture_dir / f"{safe_id}.json"
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")

        closing = ClosingOddsReference(
            decision_id=decision.decision_id,
            fixture_id=decision.fixture_id,
            market_key=decision.market_key,
            selection_key=decision.selection_key,
            source_provider="Pinnacle via odds-api.net",
            source_reference=f"{evidence_path.as_posix()};payload_sha256={evidence['payload_sha256']}",
            observed_at_utc=captured_at.isoformat(),
            fixture_kickoff_utc=decision.fixture_kickoff_utc,
            decimal_odds=over_odds,
            source_authorized=True,
        )
        ledger.append_closing_odds(closing)
        _append_closing_attempt(attempt_log_path, {
            **attempt,
            "outcome": "ODDS_API_CAPTURED_VALID",
            "evidence_path": evidence_path.as_posix(),
            "evidence_payload_sha256": evidence["payload_sha256"],
        })
        result["captured_new"] += 1
        result["evidence_paths"].append(evidence_path.as_posix())

    return result


def main() -> None:
    result = capture_due_via_odds_api_net(
        api_football_key=os.environ.get("API_FOOTBALL_KEY", ""),
        odds_api_key=os.environ.get("ODDS_API_NET_KEY", ""),
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
