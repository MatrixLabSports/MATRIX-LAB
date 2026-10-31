from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

MIN_SETTLEMENT_AGE_MINUTES = 45


def _utc(value: Any) -> datetime:
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("TIMESTAMP_MUST_BE_AWARE")
    return dt.astimezone(timezone.utc)


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _ledger_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        fid = str(row.get("fixture_id") or "")
        if not fid:
            raise ValueError("SETTLEMENT_LEDGER_FIXTURE_ID_MISSING")
        if fid in ids:
            raise ValueError("SETTLEMENT_LEDGER_DUPLICATE_FIXTURE")
        ids.add(fid)
    return ids


@dataclass(frozen=True)
class SupervisorDecision:
    due: bool
    reason: str
    checked_at_utc: str
    frozen_event_count: int
    settled_event_count: int
    unresolved_event_count: int
    eligible_unresolved_count: int
    last_sync_at_utc: str | None
    last_sync_age_seconds: int | None
    minimum_age_minutes: int
    real_money: str = "BLOCKED"
    automatic_wagering: bool = False


def assess_due(
    root: Path,
    *,
    now_utc: datetime | None = None,
    minimum_age_minutes: int = MIN_SETTLEMENT_AGE_MINUTES,
) -> SupervisorDecision:
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    if minimum_age_minutes < 5:
        raise ValueError("MINIMUM_AGE_TOO_SMALL")

    freeze_path = root / "prospective_market_freeze" / "freeze.json"
    if not freeze_path.exists():
        return SupervisorDecision(
            False, "NO_PROSPECTIVE_FREEZE", now.isoformat(), 0, 0, 0, 0,
            None, None, minimum_age_minutes,
        )

    freeze = _load(freeze_path)
    rows = freeze.get("rows")
    if not isinstance(rows, list):
        raise ValueError("FREEZE_ROWS_MISSING")

    ledger_ids = _ledger_ids(root / "prospective_market_freeze" / "settlement_ledger.jsonl")
    unresolved: list[Mapping[str, Any]] = []
    eligible: list[str] = []

    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("FREEZE_ROW_INVALID")
        fid = str(row.get("fixture_id") or "")
        if not fid:
            raise ValueError("FREEZE_FIXTURE_ID_MISSING")
        if fid in ledger_ids:
            continue
        unresolved.append(row)
        kickoff = _utc(row.get("kickoff_utc"))
        if now >= kickoff + timedelta(minutes=120):
            eligible.append(fid)

    sync_path = root / "prospective_market_freeze" / "settlement_sync_last.json"
    last_sync: datetime | None = None
    age_seconds: int | None = None
    if sync_path.exists():
        sync = _load(sync_path)
        raw = sync.get("run_at_utc")
        if raw:
            last_sync = _utc(raw)
            age_seconds = max(0, int((now - last_sync).total_seconds()))

    if not unresolved:
        due = False
        reason = "ALL_FROZEN_EVENTS_SETTLED"
    elif not eligible:
        due = False
        reason = "NO_ELIGIBLE_FINAL_WINDOWS"
    elif last_sync is None:
        due = True
        reason = "ELIGIBLE_NO_PRIOR_SYNC"
    elif age_seconds is not None and age_seconds < minimum_age_minutes * 60:
        due = False
        reason = "RECENT_SETTLEMENT_SYNC"
    else:
        due = True
        reason = "ELIGIBLE_AND_SETTLEMENT_STALE"

    return SupervisorDecision(
        due=due,
        reason=reason,
        checked_at_utc=now.isoformat(),
        frozen_event_count=len(rows),
        settled_event_count=len(ledger_ids),
        unresolved_event_count=len(unresolved),
        eligible_unresolved_count=len(eligible),
        last_sync_at_utc=last_sync.isoformat() if last_sync else None,
        last_sync_age_seconds=age_seconds,
        minimum_age_minutes=minimum_age_minutes,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="evidence/api_football",
        help="API-Football evidence root",
    )
    parser.add_argument("--minimum-age-minutes", type=int, default=MIN_SETTLEMENT_AGE_MINUTES)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    decision = assess_due(
        Path(args.root),
        minimum_age_minutes=args.minimum_age_minutes,
    )
    payload = asdict(decision)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
