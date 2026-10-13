from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

import requests

from app.research.football.prospective_ledger import (
    ClosingOddsReference,
    FootballProspectiveEvidenceLedger,
    FrozenProspectiveDecision,
)
from matrix_elite.market_history import market_snapshot_sha256
from matrix_elite.odds import OddsSnapshot, fair_market_probabilities

BOGOTA = ZoneInfo("America/Bogota")
API_BASE = "https://v3.football.api-sports.io"
PINNACLE_BOOKMAKER_ID = 4
PINNACLE_BOOKMAKER_NAME = "Pinnacle"
MARKET_KEY = "over_2_5"
SELECTION_KEY = "over"
MODEL_VERSION = "calibrated_log_pool_v1_over_2_5"
CLOSE_WINDOW_MINUTES = 15
MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS = 10_800
MIN_CLV_CLOSING_OBSERVATIONS = 300

DEFAULT_ROOT = Path("evidence/clv/football/over_2_5")
DEFAULT_LEDGER = DEFAULT_ROOT / "prospective_clv_ledger.jsonl"
DEFAULT_CAPTURE_DIR = DEFAULT_ROOT / "closing_captures"
DEFAULT_STATE = DEFAULT_ROOT / "state.json"


def _aware(value: Any, *, name: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name}_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    raw = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return payload


def _existing_decisions_and_closings(
    ledger: FootballProspectiveEvidenceLedger,
) -> tuple[dict[str, FrozenProspectiveDecision], set[str]]:
    decisions: dict[str, FrozenProspectiveDecision] = {}
    closings: set[str] = set()
    for event in ledger.load_events():
        if event.event_type == "DECISION_FROZEN":
            decision = FrozenProspectiveDecision.from_mapping(event.payload)
            decisions[decision.decision_id] = decision
        elif event.event_type == "CLOSING_ODDS_RECORDED":
            closing = ClosingOddsReference.from_mapping(event.payload)
            closings.add(closing.decision_id)
    return decisions, closings


def freeze_new_decisions(
    report_path: Path,
    ledger: FootballProspectiveEvidenceLedger,
) -> dict[str, int]:
    report = _load_json(report_path)
    if report.get("market") != "OVER_2_5":
        raise ValueError("CLV_REPORT_MARKET_MISMATCH")
    protections = report.get("protections") or {}
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("CLV_ODDS_TO_PROBABILITY_PROTECTION_MISSING")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("CLV_REAL_MONEY_MUST_REMAIN_BLOCKED")

    existing, _ = _existing_decisions_and_closings(ledger)
    natural_keys = {
        (d.fixture_id, d.market_key, d.selection_key, d.model_version)
        for d in existing.values()
    }
    report_digest = str(report.get("sha256_without_self") or "").lower()
    if len(report_digest) != 64:
        report_digest = _file_sha256(report_path)

    frozen = 0
    skipped_existing = 0
    blocked_missing_entry_timestamp = 0
    blocked_invalid = 0

    for row in report.get("bet_shadow") or []:
        if not isinstance(row, Mapping):
            continue
        fixture_id = str(row.get("fixture_id") or "").strip()
        offer = row.get("best_policy_offer")
        if not fixture_id or not isinstance(offer, Mapping):
            blocked_invalid += 1
            continue

        captured_at = str(
            offer.get("odds_captured_at_utc")
            or row.get("odds_captured_at_utc")
            or ""
        ).strip()
        quote_sha = str(offer.get("quote_evidence_sha256") or "").lower()
        if not captured_at or len(quote_sha) != 64:
            # Anti-backfill: older reports without a physical quote timestamp/hash
            # are never reconstructed after the fact for CLV.
            blocked_missing_entry_timestamp += 1
            continue

        natural_key = (fixture_id, MARKET_KEY, SELECTION_KEY, MODEL_VERSION)
        if natural_key in natural_keys:
            skipped_existing += 1
            continue

        try:
            kickoff = _aware(row.get("kickoff_utc"), name="KICKOFF")
            decision_at = _aware(captured_at, name="ENTRY_CAPTURE")
            p_matrix = float(row.get("p_over_2_5"))
            decimal_odds = float(offer.get("decimal_odds"))
            if decision_at >= kickoff:
                raise ValueError("ENTRY_CAPTURE_NOT_PREMATCH")
            if not (0.0 <= p_matrix <= 1.0) or decimal_odds <= 1.0:
                raise ValueError("ENTRY_VALUES_INVALID")
            bookmaker = str(offer.get("bookmaker_name") or "").strip()
            if not bookmaker:
                raise ValueError("ENTRY_BOOKMAKER_MISSING")

            decision_id = "clv-over25-" + hashlib.sha256(
                f"{fixture_id}|{MARKET_KEY}|{SELECTION_KEY}|{MODEL_VERSION}".encode("utf-8")
            ).hexdigest()
            source_reference = (
                f"{report_path.as_posix()};fixture={fixture_id};"
                f"entry_raw_sha256={row.get('raw_sha256')};quote_sha256={quote_sha}"
            )
            decision = FrozenProspectiveDecision(
                decision_id=decision_id,
                fixture_id=fixture_id,
                market_key=MARKET_KEY,
                selection_key=SELECTION_KEY,
                model_version=MODEL_VERSION,
                model_probability=p_matrix,
                decision_at_utc=decision_at.isoformat(),
                fixture_kickoff_utc=kickoff.isoformat(),
                block_id=str(report.get("target_date_bogota") or kickoff.astimezone(BOGOTA).date()),
                odds_snapshot_sha256=quote_sha,
                odds_observed_at_utc=decision_at.isoformat(),
                decimal_odds=decimal_odds,
                odds_source_provider=bookmaker,
                odds_source_reference=source_reference,
                odds_source_authorized=True,
                model_input_sha256s=(report_digest,),
            )
            ledger.append_decision(decision)
            natural_keys.add(natural_key)
            frozen += 1
        except (TypeError, ValueError):
            blocked_invalid += 1

    return {
        "frozen_new": frozen,
        "skipped_existing": skipped_existing,
        "blocked_missing_entry_timestamp": blocked_missing_entry_timestamp,
        "blocked_invalid": blocked_invalid,
    }


def _extract_pinnacle_over25_market(
    payload: Mapping[str, Any],
) -> tuple[float, float, datetime] | None:
    errors = payload.get("errors")
    if errors not in ({}, [], None):
        return None
    for fixture_row in payload.get("response") or []:
        if not isinstance(fixture_row, Mapping):
            continue
        update_raw = str(fixture_row.get("update") or "").strip()
        if not update_raw:
            continue
        provider_update = _aware(update_raw, name="PINNACLE_PROVIDER_UPDATE")
        for bookmaker in fixture_row.get("bookmakers") or []:
            if not isinstance(bookmaker, Mapping):
                continue
            if str(bookmaker.get("id")) != str(PINNACLE_BOOKMAKER_ID):
                continue
            if str(bookmaker.get("name") or "").strip().casefold() != PINNACLE_BOOKMAKER_NAME.casefold():
                continue
            for bet in bookmaker.get("bets") or []:
                if not isinstance(bet, Mapping):
                    continue
                try:
                    bet_id = int(bet.get("id"))
                except (TypeError, ValueError):
                    continue
                if bet_id != 5 or str(bet.get("name") or "").strip().casefold() != "goals over/under":
                    continue
                over = under = None
                for value in bet.get("values") or []:
                    if not isinstance(value, Mapping):
                        continue
                    label = str(value.get("value") or "").strip().casefold()
                    try:
                        price = float(value.get("odd"))
                    except (TypeError, ValueError):
                        continue
                    if price <= 1.0:
                        continue
                    if label == "over 2.5":
                        over = price
                    elif label == "under 2.5":
                        under = price
                if over is not None and under is not None:
                    return over, under, provider_update
    return None


def capture_due_closing_lines(
    ledger: FootballProspectiveEvidenceLedger,
    capture_dir: Path,
    *,
    api_key: str,
    now: datetime,
    session: Any | None = None,
    capture_clock: Any | None = None,
) -> dict[str, Any]:
    reference = now.astimezone(timezone.utc)
    clock = capture_clock or (lambda: datetime.now(timezone.utc))
    decisions, closings = _existing_decisions_and_closings(ledger)
    due: list[FrozenProspectiveDecision] = []
    missed_after_kickoff = 0

    for decision in decisions.values():
        if decision.decision_id in closings:
            continue
        kickoff = _aware(decision.fixture_kickoff_utc, name="KICKOFF")
        lead = kickoff - reference
        if lead.total_seconds() <= 0:
            missed_after_kickoff += 1
            continue
        if lead <= timedelta(minutes=CLOSE_WINDOW_MINUTES):
            due.append(decision)

    if due and not str(api_key or "").strip():
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED_FOR_CLV_CLOSE")

    client = session or requests.Session()
    capture_dir.mkdir(parents=True, exist_ok=True)
    calls = 0
    captured = 0
    blocked_provider_error = 0
    blocked_market_incomplete = 0
    blocked_stale_provider_quote = 0
    blocked_temporal = 0
    evidence_paths: list[str] = []

    for decision in sorted(due, key=lambda d: (d.fixture_kickoff_utc, d.fixture_id)):
        response = client.get(
            API_BASE + "/odds",
            headers={"x-apisports-key": str(api_key).strip()},
            params={"fixture": decision.fixture_id, "bookmaker": PINNACLE_BOOKMAKER_ID},
            timeout=(10, 30),
        )
        calls += 1
        captured_at = clock().astimezone(timezone.utc).replace(microsecond=0)
        if captured_at.tzinfo is None or captured_at.utcoffset() is None:
            raise ValueError("CAPTURE_CLOCK_MUST_BE_TIMEZONE_AWARE")
        body = bytes(response.content)
        raw_sha256 = hashlib.sha256(body).hexdigest()
        try:
            payload = response.json()
        except Exception:
            payload = {}

        if response.status_code >= 300 or not isinstance(payload, Mapping):
            blocked_provider_error += 1
            continue
        parsed = _extract_pinnacle_over25_market(payload)
        if parsed is None:
            blocked_market_incomplete += 1
            continue
        over_odds, under_odds, provider_update = parsed
        kickoff = _aware(decision.fixture_kickoff_utc, name="KICKOFF")

        if captured_at >= kickoff or provider_update >= kickoff or provider_update > captured_at:
            blocked_temporal += 1
            continue
        provider_quote_age_seconds = int((captured_at - provider_update).total_seconds())
        if provider_quote_age_seconds > MAX_PINNACLE_PROVIDER_QUOTE_AGE_SECONDS:
            blocked_stale_provider_quote += 1
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
        snapshot_sha256 = market_snapshot_sha256(snapshots)
        fair_over = float(fair["over_2_5"])
        probability_clv = fair_over - (1.0 / decision.decimal_odds)
        log_price_clv = math.log(decision.decimal_odds / over_odds)
        fair_odds_clv_ratio = decision.decimal_odds * fair_over - 1.0
        lead_seconds = int((kickoff - captured_at).total_seconds())

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
                "transport": "API-Football /odds",
                "direct_pinnacle_api_connection": False,
                "source_quality_flag": "SHARP_PINNACLE_VIA_API_FOOTBALL",
                "system_captured_at_utc": captured_at.isoformat(),
                "provider_quote_updated_at_utc": provider_update.isoformat(),
                "provider_quote_age_seconds": provider_quote_age_seconds,
                "kickoff_utc": kickoff.isoformat(),
                "capture_lead_seconds": lead_seconds,
                "complete_market_snapshot": True,
                "over_2_5_decimal_odds": over_odds,
                "under_2_5_decimal_odds": under_odds,
                "fair_over_2_5_probability_devigged": fair_over,
                "devig_method": "MULTIPLICATIVE",
                "market_snapshot_sha256": snapshot_sha256,
                "raw_payload_sha256": raw_sha256,
            },
            "clv": {
                "log_price_clv": log_price_clv,
                "probability_clv_vs_devigged_close": probability_clv,
                "fair_odds_clv_ratio": fair_odds_clv_ratio,
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
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        source_reference = (
            f"{evidence_path.as_posix()};payload_sha256={evidence['payload_sha256']};"
            f"source_quality_flag=SHARP_PINNACLE_VIA_API_FOOTBALL"
        )
        closing = ClosingOddsReference(
            decision_id=decision.decision_id,
            fixture_id=decision.fixture_id,
            market_key=decision.market_key,
            selection_key=decision.selection_key,
            source_provider="Pinnacle via API-Football",
            source_reference=source_reference,
            observed_at_utc=captured_at.isoformat(),
            fixture_kickoff_utc=decision.fixture_kickoff_utc,
            decimal_odds=over_odds,
            source_authorized=True,
        )
        ledger.append_closing_odds(closing)
        captured += 1
        evidence_paths.append(evidence_path.as_posix())

    return {
        "due_count": len(due),
        "network_calls": calls,
        "captured_new": captured,
        "missed_after_kickoff": missed_after_kickoff,
        "blocked_provider_error": blocked_provider_error,
        "blocked_market_incomplete": blocked_market_incomplete,
        "blocked_stale_provider_quote": blocked_stale_provider_quote,
        "blocked_temporal": blocked_temporal,
        "evidence_paths": evidence_paths,
    }


def build_state(
    ledger: FootballProspectiveEvidenceLedger,
    capture_dir: Path,
    *,
    freeze_result: Mapping[str, Any],
    close_result: Mapping[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    audit = ledger.audit()
    remaining = max(0, MIN_CLV_CLOSING_OBSERVATIONS - audit.closing_odds_count)
    metrics_opened = audit.closing_odds_count >= MIN_CLV_CLOSING_OBSERVATIONS
    metrics: dict[str, Any] | None = None

    if metrics_opened and audit.decision_count:
        summary = ledger.performance_summary(
            market_key=MARKET_KEY,
            model_version=MODEL_VERSION,
        )
        devig_values: list[float] = []
        for path in sorted(capture_dir.glob("*.json")):
            try:
                payload = _load_json(path)
                value = payload.get("clv", {}).get("probability_clv_vs_devigged_close")
                if isinstance(value, (int, float)):
                    devig_values.append(float(value))
            except Exception:
                continue
        metrics = {
            "mean_log_clv": summary.mean_log_clv,
            "mean_log_clv_ci_low": summary.mean_log_clv_ci_low,
            "mean_log_clv_ci_high": summary.mean_log_clv_ci_high,
            "mean_probability_clv_vs_devigged_close": (
                sum(devig_values) / len(devig_values) if devig_values else None
            ),
            "devigged_clv_observation_count": len(devig_values),
        }

    return {
        "schema": "MATRIX_FOOTBALL_CLV_TRACKING_STATE_V1",
        "generated_at_utc": generated_at.astimezone(timezone.utc).replace(microsecond=0).isoformat(),
        "market_key": MARKET_KEY,
        "model_version": MODEL_VERSION,
        "closing_reference_choice": "OPTION_B_PINNACLE",
        "closing_reference_transport": "API_FOOTball /odds bookmaker_id=4",
        "direct_pinnacle_api_connection": False,
        "source_quality_flag": "SHARP_PINNACLE_VIA_API_FOOTBALL",
        "ledger_path": ledger.path.as_posix(),
        "ledger_sha256": audit.ledger_sha256,
        "decision_count": audit.decision_count,
        "closing_odds_count": audit.closing_odds_count,
        "minimum_clv_closing_observations": MIN_CLV_CLOSING_OBSERVATIONS,
        "remaining_to_open_metrics": remaining,
        "metrics_opened": metrics_opened,
        "metrics": metrics,
        "freeze_cycle": dict(freeze_result),
        "closing_cycle": dict(close_result),
        "status": "CLV_METRICS_OPEN" if metrics_opened else "ACCUMULATING_SEALED_UNTIL_300",
        "protections": {
            "historical_backfill_without_physical_entry_timestamp": "FORBIDDEN",
            "post_kickoff_closing_line": "FORBIDDEN",
            "incomplete_market_devig": "FORBIDDEN",
            "clv_from_raw_overround_probability": "FORBIDDEN",
            "odds_used_to_generate_probability": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED",
        },
    }


def run_cycle(
    *,
    report_path: Path | None,
    ledger_path: Path = DEFAULT_LEDGER,
    capture_dir: Path = DEFAULT_CAPTURE_DIR,
    state_path: Path = DEFAULT_STATE,
    api_key: str = "",
    now: datetime | None = None,
    session: Any | None = None,
    capture_clock: Any | None = None,
) -> dict[str, Any]:
    reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ledger = FootballProspectiveEvidenceLedger(ledger_path)

    if report_path is not None and report_path.is_file():
        freeze_result = freeze_new_decisions(report_path, ledger)
    else:
        freeze_result = {
            "frozen_new": 0,
            "skipped_existing": 0,
            "blocked_missing_entry_timestamp": 0,
            "blocked_invalid": 0,
            "report_missing": True,
        }

    close_result = capture_due_closing_lines(
        ledger,
        capture_dir,
        api_key=api_key,
        now=reference,
        session=session,
        capture_clock=capture_clock,
    )
    state = build_state(
        ledger,
        capture_dir,
        freeze_result=freeze_result,
        close_result=close_result,
        generated_at=reference,
    )
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return state


def _default_report_for_today() -> Path:
    day = str(datetime.now(timezone.utc).astimezone(BOGOTA).date())
    return Path(
        f"evidence/api_football/daily_prematch_reports/{day}/"
        "over25_shadow_ev/MATRIX_FOOTBALL_DAILY_OVER25_GOVERNED_SHADOW_EV.json"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-path", default="")
    parser.add_argument("--ledger-path", default=str(DEFAULT_LEDGER))
    parser.add_argument("--capture-dir", default=str(DEFAULT_CAPTURE_DIR))
    parser.add_argument("--state-path", default=str(DEFAULT_STATE))
    args = parser.parse_args()

    report_path = Path(args.report_path) if args.report_path else _default_report_for_today()
    state = run_cycle(
        report_path=report_path if report_path.is_file() else None,
        ledger_path=Path(args.ledger_path),
        capture_dir=Path(args.capture_dir),
        state_path=Path(args.state_path),
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
    )
    print(json.dumps({
        "status": state["status"],
        "decision_count": state["decision_count"],
        "closing_odds_count": state["closing_odds_count"],
        "remaining_to_open_metrics": state["remaining_to_open_metrics"],
        "metrics_opened": state["metrics_opened"],
        "network_calls": state["closing_cycle"]["network_calls"],
        "captured_new": state["closing_cycle"]["captured_new"],
        "real_money": state["protections"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
