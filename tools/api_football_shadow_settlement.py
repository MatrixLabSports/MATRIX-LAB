from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

import requests

from tools.api_football_canonicalize_analysis_inputs import load_chunked_canonical_bundle


BASE_URL = "https://v3.football.api-sports.io"
FINAL_LOOKUP_DELAY_MINUTES = 120
MAX_REQUESTS_DEFAULT = 120
TIMEOUT_SECONDS = 20.0

STANDARD_FINAL = {"FT"}
NONSTANDARD_TERMINAL = {
    "AET",
    "PEN",
    "PST",
    "CANC",
    "ABD",
    "AWD",
    "WO",
    "SUSP",
    "INT",
}


def _utc(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_TIMEZONE_AWARE")
    return parsed.astimezone(timezone.utc)


def _canonical(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _record_sha(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("record_sha256", None)
    return _sha(body)


def _settlement_id(payload: Mapping[str, Any]) -> str:
    body = dict(payload)
    body.pop("settlement_id", None)
    body.pop("record_sha256", None)
    body.pop("previous_record_sha256", None)
    return _sha({
        "schema": "MATRIX_API_FOOTBALL_SHADOW_SETTLEMENT_ID_V1",
        "payload": body,
    })


@dataclass(frozen=True)
class ShadowSettlementLedgerAudit:
    records: int
    unique_fixtures: int
    hash_chain_verified: bool
    outcomes_used_for_metrics: int


class ShadowSettlementLedger:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        previous: str | None = None
        seen: set[str] = set()
        for line_number, raw in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as error:
                raise ValueError(
                    f"INVALID_SHADOW_SETTLEMENT_JSON:{line_number}"
                ) from error

            fixture_id = str(row.get("fixture_id") or "")
            if not fixture_id or fixture_id in seen:
                raise ValueError("DUPLICATE_OR_MISSING_SETTLEMENT_FIXTURE")
            if row.get("previous_record_sha256") != previous:
                raise ValueError("SHADOW_SETTLEMENT_HASH_CHAIN_BROKEN")
            if row.get("record_sha256") != _record_sha(row):
                raise ValueError("SHADOW_SETTLEMENT_RECORD_SHA_MISMATCH")
            if row.get("settlement_id") != _settlement_id(row):
                raise ValueError("SHADOW_SETTLEMENT_ID_MISMATCH")
            if row.get("terminal_status") != "FT":
                raise ValueError("SHADOW_SETTLEMENT_REQUIRES_STANDARD_FT")
            if row.get("model_status") != "EXPERIMENTAL_NOT_PROMOTED":
                raise ValueError("SHADOW_SETTLEMENT_MODEL_STATUS_MISMATCH")
            if row.get("metrics_opened") is not False:
                raise ValueError("SHADOW_SETTLEMENT_METRICS_MUST_REMAIN_CLOSED")
            if row.get("used_for_metrics") is not False:
                raise ValueError("SHADOW_SETTLEMENT_OUTCOME_MUST_NOT_AUTO_OPEN_METRICS")
            if row.get("p_matrix_status") != "NOT_GENERATED":
                raise ValueError("SHADOW_SETTLEMENT_P_MATRIX_MUST_NOT_EXIST")
            if row.get("real_money") != "BLOCKED":
                raise ValueError("SHADOW_SETTLEMENT_REAL_MONEY_MUST_BE_BLOCKED")

            outcomes = row.get("outcomes")
            if not isinstance(outcomes, Mapping):
                raise ValueError("SHADOW_SETTLEMENT_OUTCOMES_REQUIRED")
            required_markets = {
                "home_win",
                "draw",
                "away_win",
                "over_1_5",
                "over_2_5",
                "over_3_5",
                "btts",
            }
            if set(outcomes) != required_markets:
                raise ValueError("SHADOW_SETTLEMENT_OUTCOME_MARKETS_MISMATCH")
            if not all(isinstance(value, bool) for value in outcomes.values()):
                raise ValueError("SHADOW_SETTLEMENT_OUTCOMES_MUST_BE_BOOLEAN")

            previous = str(row["record_sha256"])
            seen.add(fixture_id)
            rows.append(row)
        return rows

    def append(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        rows = self.load()
        fixture_id = str(payload.get("fixture_id") or "")
        if not fixture_id:
            raise ValueError("SETTLEMENT_FIXTURE_ID_REQUIRED")
        if any(str(row["fixture_id"]) == fixture_id for row in rows):
            raise ValueError("DUPLICATE_SHADOW_SETTLEMENT_FIXTURE")

        row = dict(payload)
        row["previous_record_sha256"] = (
            rows[-1]["record_sha256"] if rows else None
        )
        row["settlement_id"] = _settlement_id(row)
        row["record_sha256"] = _record_sha(row)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(_canonical(row) + "\n")
            handle.flush()
        self.load()
        return row

    def audit(self) -> ShadowSettlementLedgerAudit:
        rows = self.load()
        return ShadowSettlementLedgerAudit(
            records=len(rows),
            unique_fixtures=len({str(row["fixture_id"]) for row in rows}),
            hash_chain_verified=True,
            outcomes_used_for_metrics=sum(
                1 for row in rows if row.get("used_for_metrics") is True
            ),
        )


def build_shadow_settlement_queue(
    *,
    shadow: Mapping[str, Any],
    canonical_bundle: Mapping[str, Any],
    ledger_records: list[Mapping[str, Any]],
    now_utc: datetime,
) -> dict[str, Any]:
    if shadow.get("model_role") != "RESEARCH_SHADOW_BASELINE":
        raise ValueError("SHADOW_MODEL_ROLE_MISMATCH")
    if shadow.get("model_status") != "EXPERIMENTAL_NOT_PROMOTED":
        raise ValueError("SHADOW_MODEL_STATUS_MISMATCH")
    if shadow.get("p_matrix_status") != "NOT_GENERATED":
        raise ValueError("P_MATRIX_MUST_REMAIN_NOT_GENERATED")
    protections = shadow.get("protections")
    if not isinstance(protections, Mapping):
        raise ValueError("SHADOW_PROTECTIONS_MISSING")
    if protections.get("outcomes_used_to_generate_probability") is not False:
        raise ValueError("SHADOW_OUTCOME_LEAKAGE_DETECTED")
    if protections.get("odds_used_to_generate_probability") is not False:
        raise ValueError("SHADOW_ODDS_LEAKAGE_DETECTED")
    if protections.get("real_money") != "BLOCKED":
        raise ValueError("REAL_MONEY_MUST_BE_BLOCKED")

    now = now_utc.astimezone(timezone.utc)
    settled = {str(row.get("fixture_id") or "") for row in ledger_records}
    canonical_by_fixture = {
        str(row.get("fixture_id")): row
        for row in canonical_bundle.get("inputs", [])
        if isinstance(row, Mapping)
    }

    items: list[dict[str, Any]] = []
    for row in shadow.get("rows", []):
        if not isinstance(row, Mapping):
            continue
        fixture_id = str(row.get("fixture_id") or "")
        canonical = canonical_by_fixture.get(fixture_id)
        if canonical is None:
            raise ValueError(f"CANONICAL_FIXTURE_MISSING:{fixture_id}")

        kickoff = _utc(row["kickoff_utc"])
        lookup_after = kickoff + timedelta(minutes=FINAL_LOOKUP_DELAY_MINUTES)

        if fixture_id in settled:
            status = "SETTLED"
            blocker = None
        elif now <= kickoff:
            status = "WAITING_KICKOFF"
            blocker = None
        elif now < lookup_after:
            status = "WAITING_FINAL_WINDOW"
            blocker = None
        else:
            status = "READY_RESULT_LOOKUP"
            blocker = None

        items.append({
            "fixture_id": fixture_id,
            "target_key": row.get("target_key"),
            "kickoff_utc": row.get("kickoff_utc"),
            "lookup_after_utc": lookup_after.isoformat(),
            "freeze_at_utc": row.get("freeze_at_utc"),
            "input_sha256": row.get("input_sha256"),
            "prediction_fingerprint": _sha(dict(row)),
            "model_name": row.get("model_name"),
            "model_role": row.get("model_role"),
            "model_status": row.get("model_status"),
            "home_team_id": str(canonical.get("home_team_id") or ""),
            "home_team_name": canonical.get("home_team_name"),
            "away_team_id": str(canonical.get("away_team_id") or ""),
            "away_team_name": canonical.get("away_team_name"),
            "markets": dict(row.get("markets") or {}),
            "status": status,
            "blocker": blocker,
        })

    items.sort(key=lambda item: (item["kickoff_utc"], item["fixture_id"]))
    counts = {
        status: sum(1 for item in items if item["status"] == status)
        for status in (
            "SETTLED",
            "WAITING_KICKOFF",
            "WAITING_FINAL_WINDOW",
            "READY_RESULT_LOOKUP",
        )
    }

    return {
        "schema": "MATRIX_API_FOOTBALL_SHADOW_SETTLEMENT_QUEUE_V1",
        "generated_at_utc": now.replace(microsecond=0).isoformat(),
        "model_role": "RESEARCH_SHADOW_BASELINE",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "p_matrix_status": "NOT_GENERATED",
        "final_lookup_delay_minutes": FINAL_LOOKUP_DELAY_MINUTES,
        "fixture_count": len(items),
        "counts": counts,
        "items": items,
        "metrics_opened": False,
        "outcomes_used_for_metrics": 0,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _provider_errors_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (list, dict)):
        return len(value) == 0
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _exact_provider_fixture(
    payload: Mapping[str, Any],
    fixture_id: str,
) -> Mapping[str, Any]:
    if not _provider_errors_empty(payload.get("errors")):
        raise ValueError("API_FOOTBALL_PROVIDER_ERROR_PRESENT")
    rows = payload.get("response")
    if not isinstance(rows, list):
        raise ValueError("API_FOOTBALL_FIXTURE_RESPONSE_NOT_LIST")
    exact = [
        row
        for row in rows
        if isinstance(row, Mapping)
        and str(
            (row.get("fixture") or {}).get("id")
            if isinstance(row.get("fixture"), Mapping)
            else ""
        )
        == fixture_id
    ]
    if len(exact) != 1:
        raise ValueError(
            f"API_FOOTBALL_EXACT_FIXTURE_REQUIRED:{fixture_id}:{len(exact)}"
        )
    return exact[0]


def settlement_from_final_fixture(
    *,
    queue_item: Mapping[str, Any],
    provider_fixture: Mapping[str, Any],
    settled_at_utc: datetime,
    source_reference: str,
    source_payload_sha256: str,
) -> dict[str, Any]:
    if queue_item.get("status") != "READY_RESULT_LOOKUP":
        raise ValueError("SHADOW_SETTLEMENT_ITEM_NOT_READY")
    fixture_id = str(queue_item.get("fixture_id") or "")

    fixture = provider_fixture.get("fixture")
    teams = provider_fixture.get("teams")
    score = provider_fixture.get("score")
    goals = provider_fixture.get("goals")
    if not isinstance(fixture, Mapping):
        raise ValueError("FINAL_FIXTURE_METADATA_MISSING")
    if not isinstance(teams, Mapping):
        raise ValueError("FINAL_FIXTURE_TEAMS_MISSING")
    if not isinstance(score, Mapping):
        raise ValueError("FINAL_FIXTURE_SCORE_MISSING")

    if str(fixture.get("id") or "") != fixture_id:
        raise ValueError("FINAL_FIXTURE_IDENTITY_MISMATCH")

    home = teams.get("home")
    away = teams.get("away")
    if not isinstance(home, Mapping) or not isinstance(away, Mapping):
        raise ValueError("FINAL_FIXTURE_TEAM_IDENTITIES_MISSING")
    if str(home.get("id") or "") != str(queue_item.get("home_team_id") or ""):
        raise ValueError("FINAL_FIXTURE_HOME_TEAM_ID_MISMATCH")
    if str(away.get("id") or "") != str(queue_item.get("away_team_id") or ""):
        raise ValueError("FINAL_FIXTURE_AWAY_TEAM_ID_MISMATCH")

    status = fixture.get("status")
    if not isinstance(status, Mapping):
        raise ValueError("FINAL_FIXTURE_STATUS_MISSING")
    short = str(status.get("short") or "").strip().upper()
    if short != "FT":
        raise ValueError("SHADOW_SETTLEMENT_NOT_STANDARD_FT:" + short)

    fulltime = score.get("fulltime")
    if not isinstance(fulltime, Mapping):
        raise ValueError("FINAL_FIXTURE_FULLTIME_SCORE_MISSING")
    home_goals = fulltime.get("home")
    away_goals = fulltime.get("away")
    if (
        isinstance(home_goals, bool)
        or isinstance(away_goals, bool)
        or not isinstance(home_goals, int)
        or not isinstance(away_goals, int)
        or home_goals < 0
        or away_goals < 0
    ):
        raise ValueError("FINAL_FIXTURE_FULLTIME_SCORE_INVALID")

    if isinstance(goals, Mapping):
        provider_home = goals.get("home")
        provider_away = goals.get("away")
        if (
            isinstance(provider_home, int)
            and not isinstance(provider_home, bool)
            and isinstance(provider_away, int)
            and not isinstance(provider_away, bool)
            and (provider_home != home_goals or provider_away != away_goals)
        ):
            raise ValueError("FINAL_FIXTURE_GOALS_FULLTIME_CONFLICT")

    total = home_goals + away_goals
    outcomes = {
        "home_win": home_goals > away_goals,
        "draw": home_goals == away_goals,
        "away_win": away_goals > home_goals,
        "over_1_5": total > 1.5,
        "over_2_5": total > 2.5,
        "over_3_5": total > 3.5,
        "btts": home_goals > 0 and away_goals > 0,
    }

    markets = queue_item.get("markets")
    if not isinstance(markets, Mapping):
        raise ValueError("SHADOW_PREDICTION_MARKETS_MISSING")
    if set(markets) != set(outcomes):
        raise ValueError("SHADOW_MARKET_OUTCOME_BINDING_MISMATCH")

    return {
        "schema": "MATRIX_API_FOOTBALL_SHADOW_SETTLEMENT_RECORD_V1",
        "fixture_id": fixture_id,
        "target_key": queue_item.get("target_key"),
        "kickoff_utc": queue_item.get("kickoff_utc"),
        "freeze_at_utc": queue_item.get("freeze_at_utc"),
        "input_sha256": queue_item.get("input_sha256"),
        "prediction_fingerprint": queue_item.get("prediction_fingerprint"),
        "model_name": queue_item.get("model_name"),
        "model_role": queue_item.get("model_role"),
        "model_status": queue_item.get("model_status"),
        "p_matrix_status": "NOT_GENERATED",
        "settled_at_utc": settled_at_utc.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat(),
        "terminal_status": "FT",
        "home_team_id": queue_item.get("home_team_id"),
        "home_team_name": queue_item.get("home_team_name"),
        "away_team_id": queue_item.get("away_team_id"),
        "away_team_name": queue_item.get("away_team_name"),
        "fulltime_home_goals": home_goals,
        "fulltime_away_goals": away_goals,
        "outcomes": outcomes,
        "result_source_provider": "api_football",
        "result_source_reference": source_reference,
        "result_payload_sha256": source_payload_sha256,
        "metrics_opened": False,
        "used_for_metrics": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def sync_shadow_settlements(
    *,
    queue: Mapping[str, Any],
    ledger: ShadowSettlementLedger,
    api_key: str,
    raw_dir: Path,
    now_utc: datetime,
    session: Any | None = None,
    max_requests: int = MAX_REQUESTS_DEFAULT,
) -> dict[str, Any]:
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("API_FOOTBALL_KEY_NOT_CONFIGURED")
    key.encode("ascii")
    if max_requests <= 0:
        raise ValueError("MAX_REQUESTS_MUST_BE_POSITIVE")

    now = now_utc.astimezone(timezone.utc).replace(microsecond=0)
    client = session or requests.Session()
    raw_dir.mkdir(parents=True, exist_ok=True)

    existing = {str(row.get("fixture_id") or "") for row in ledger.load()}
    settled: list[str] = []
    pending: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    skipped_already_settled: list[str] = []
    network_calls = 0
    last_rate: dict[str, str | None] = {}

    for item in queue.get("items", []) or []:
        if not isinstance(item, Mapping):
            continue
        fixture_id = str(item.get("fixture_id") or "")
        if fixture_id in existing:
            skipped_already_settled.append(fixture_id)
            continue
        if item.get("status") != "READY_RESULT_LOOKUP":
            pending.append({
                "fixture_id": fixture_id,
                "reason": str(item.get("status") or "UNKNOWN_QUEUE_STATUS"),
            })
            continue
        if network_calls >= max_requests:
            blocked.append({
                "fixture_id": fixture_id,
                "reason": "SETTLEMENT_REQUEST_BUDGET_REACHED",
            })
            continue

        response = client.get(
            BASE_URL + "/fixtures",
            headers={"x-apisports-key": key},
            params={"id": fixture_id},
            timeout=TIMEOUT_SECONDS,
        )
        network_calls += 1
        body = bytes(response.content)
        raw_path = raw_dir / f"fixture_{fixture_id}_settlement.bin"
        raw_path.write_bytes(body)
        payload_sha = hashlib.sha256(body).hexdigest()
        try:
            payload = response.json()
        except Exception as error:
            blocked.append({
                "fixture_id": fixture_id,
                "reason": "SETTLEMENT_PROVIDER_JSON_INVALID:" + type(error).__name__,
            })
            continue

        last_rate = {
            "daily_limit": response.headers.get("x-ratelimit-requests-limit"),
            "daily_remaining": response.headers.get("x-ratelimit-requests-remaining"),
            "minute_limit": response.headers.get("X-RateLimit-Limit"),
            "minute_remaining": response.headers.get("X-RateLimit-Remaining"),
        }

        try:
            provider_fixture = _exact_provider_fixture(payload, fixture_id)
        except ValueError as error:
            blocked.append({
                "fixture_id": fixture_id,
                "reason": str(error),
                "raw_path": str(raw_path),
                "raw_sha256": payload_sha,
            })
            continue

        fixture_meta = provider_fixture.get("fixture")
        status = ""
        if isinstance(fixture_meta, Mapping):
            status_obj = fixture_meta.get("status")
            if isinstance(status_obj, Mapping):
                status = str(status_obj.get("short") or "").strip().upper()

        if status in NONSTANDARD_TERMINAL:
            blocked.append({
                "fixture_id": fixture_id,
                "reason": "NONSTANDARD_TERMINAL_REQUIRES_ADJUDICATION:" + status,
                "raw_path": str(raw_path),
                "raw_sha256": payload_sha,
            })
            continue
        if status not in STANDARD_FINAL:
            pending.append({
                "fixture_id": fixture_id,
                "reason": "RESULT_NOT_STANDARD_FINAL",
                "provider_status": status,
                "raw_path": str(raw_path),
                "raw_sha256": payload_sha,
            })
            continue

        try:
            record = settlement_from_final_fixture(
                queue_item=item,
                provider_fixture=provider_fixture,
                settled_at_utc=now,
                source_reference="/fixtures?id=" + fixture_id,
                source_payload_sha256=payload_sha,
            )
            ledger.append(record)
        except ValueError as error:
            blocked.append({
                "fixture_id": fixture_id,
                "reason": str(error),
                "raw_path": str(raw_path),
                "raw_sha256": payload_sha,
            })
            continue

        existing.add(fixture_id)
        settled.append(fixture_id)

    audit = ledger.audit()
    return {
        "schema": "MATRIX_API_FOOTBALL_SHADOW_SETTLEMENT_SYNC_V1",
        "status": "PASS",
        "run_at_utc": now.isoformat(),
        "new_settlement_count": len(settled),
        "settled_fixture_ids": settled,
        "pending": pending,
        "blocked": blocked,
        "skipped_already_settled": skipped_already_settled,
        "network_calls": network_calls,
        "last_rate_limit": last_rate,
        "ledger_records": audit.records,
        "ledger_unique_fixtures": audit.unique_fixtures,
        "ledger_hash_chain_verified": audit.hash_chain_verified,
        "outcomes_used_for_metrics": audit.outcomes_used_for_metrics,
        "metrics_opened": False,
        "p_matrix_status": "NOT_GENERATED",
        "model_status": "EXPERIMENTAL_NOT_PROMOTED",
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def run_once(
    *,
    root: Path,
    api_key: str,
    now_utc: datetime | None = None,
    session: Any | None = None,
    max_requests: int = MAX_REQUESTS_DEFAULT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    canonical_bundle, _ = load_chunked_canonical_bundle(root / "canonical_analysis")
    shadow = _load(root / "experimental_shadow" / "shadow_freeze.json")
    settlement_root = root / "shadow_settlement"
    ledger = ShadowSettlementLedger(settlement_root / "ledger.jsonl")
    queue = build_shadow_settlement_queue(
        shadow=shadow,
        canonical_bundle=canonical_bundle,
        ledger_records=ledger.load(),
        now_utc=now,
    )
    _write(settlement_root / "queue.json", queue)
    result = sync_shadow_settlements(
        queue=queue,
        ledger=ledger,
        api_key=api_key,
        raw_dir=settlement_root / "raw",
        now_utc=now,
        session=session,
        max_requests=max_requests,
    )
    _write(settlement_root / "sync_last.json", result)
    return queue, result


def main() -> None:
    root = Path("evidence/api_football")
    queue, result = run_once(
        root=root,
        api_key=os.environ.get("API_FOOTBALL_KEY", ""),
        max_requests=MAX_REQUESTS_DEFAULT,
    )
    print(json.dumps({
        "queue_fixture_count": queue["fixture_count"],
        "queue_counts": queue["counts"],
        "new_settlement_count": result["new_settlement_count"],
        "network_calls": result["network_calls"],
        "ledger_records": result["ledger_records"],
        "outcomes_used_for_metrics": result["outcomes_used_for_metrics"],
        "metrics_opened": result["metrics_opened"],
        "p_matrix_status": result["p_matrix_status"],
        "real_money": result["real_money"],
        "status": result["status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
