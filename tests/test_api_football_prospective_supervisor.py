from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.api_football_prospective_supervisor import assess_due

UTC = timezone.utc


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _freeze_row(fid: str, kickoff: datetime):
    return {
        "fixture_id": fid,
        "kickoff_utc": kickoff.astimezone(UTC).isoformat(),
    }


def _write_ledger(path: Path, fixture_ids):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps({"fixture_id": str(fid)}) for fid in fixture_ids]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def test_no_freeze_means_not_due(tmp_path: Path):
    result = assess_due(tmp_path, now_utc=datetime(2026, 9, 28, 20, 0, tzinfo=UTC))
    assert result.due is False
    assert result.reason == "NO_PROSPECTIVE_FREEZE"


def test_eligible_without_prior_sync_is_due(tmp_path: Path):
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _write_json(
        tmp_path / "prospective_market_freeze/freeze.json",
        {"rows": [_freeze_row("1", now - timedelta(hours=3))]},
    )
    result = assess_due(tmp_path, now_utc=now)
    assert result.due is True
    assert result.reason == "ELIGIBLE_NO_PRIOR_SYNC"
    assert result.eligible_unresolved_count == 1


def test_recent_sync_prevents_duplicate_api_polling(tmp_path: Path):
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _write_json(
        tmp_path / "prospective_market_freeze/freeze.json",
        {"rows": [_freeze_row("1", now - timedelta(hours=3))]},
    )
    _write_json(
        tmp_path / "prospective_market_freeze/settlement_sync_last.json",
        {"run_at_utc": (now - timedelta(minutes=20)).isoformat()},
    )
    result = assess_due(tmp_path, now_utc=now)
    assert result.due is False
    assert result.reason == "RECENT_SETTLEMENT_SYNC"


def test_stale_sync_and_eligible_fixture_is_due(tmp_path: Path):
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _write_json(
        tmp_path / "prospective_market_freeze/freeze.json",
        {"rows": [_freeze_row("1", now - timedelta(hours=3))]},
    )
    _write_json(
        tmp_path / "prospective_market_freeze/settlement_sync_last.json",
        {"run_at_utc": (now - timedelta(minutes=46)).isoformat()},
    )
    result = assess_due(tmp_path, now_utc=now)
    assert result.due is True
    assert result.reason == "ELIGIBLE_AND_SETTLEMENT_STALE"


def test_future_only_unresolved_is_not_due(tmp_path: Path):
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _write_json(
        tmp_path / "prospective_market_freeze/freeze.json",
        {"rows": [_freeze_row("1", now + timedelta(hours=5))]},
    )
    result = assess_due(tmp_path, now_utc=now)
    assert result.due is False
    assert result.reason == "NO_ELIGIBLE_FINAL_WINDOWS"


def test_settled_rows_do_not_trigger_repoll(tmp_path: Path):
    now = datetime(2026, 9, 28, 20, 0, tzinfo=UTC)
    _write_json(
        tmp_path / "prospective_market_freeze/freeze.json",
        {"rows": [_freeze_row("1", now - timedelta(hours=3))]},
    )
    _write_ledger(tmp_path / "prospective_market_freeze/settlement_ledger.jsonl", ["1"])
    result = assess_due(tmp_path, now_utc=now)
    assert result.due is False
    assert result.reason == "ALL_FROZEN_EVENTS_SETTLED"


def test_minimum_age_cannot_be_too_small(tmp_path: Path):
    try:
        assess_due(
            tmp_path,
            now_utc=datetime(2026, 9, 28, 20, 0, tzinfo=UTC),
            minimum_age_minutes=4,
        )
    except ValueError as exc:
        assert str(exc) == "MINIMUM_AGE_TOO_SMALL"
    else:
        raise AssertionError("minimum supervisor age must fail closed")
