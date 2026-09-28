from datetime import date

import pytest

from tools.cor11_cadence_update import CommitEvidence, advance, persist


def _ledger():
    return {
        "revision": "R727",
        "correction": "COR11",
        "timezone": "America/Bogota",
        "status": "IN_PROGRESS",
        "real_consecutive_days": 8,
        "target_days": 14,
        "dates": [f"2026-09-{day:02d}" for day in range(21, 29)],
        "new_physical_evidence": {},
        "rules": {
            "utc_rollover_used": False,
            "backfill": False,
            "synthetic_days": False,
            "real_money": "BLOCKED",
        },
        "cor10": {"status": "IN_PROGRESS", "genuine_future_executions": 0, "pass": False},
    }


def _evidence(day="2026-09-29"):
    return CommitEvidence(
        commit="a" * 40,
        committer_utc=f"{day}T15:00:00+00:00",
        local_date=day,
        message="evidence: real project work",
        changed_paths=("evidence/example.json",),
    )


def test_cor11_advances_only_next_real_calendar_day():
    result = advance(_ledger(), target=date(2026, 9, 29), evidence=_evidence())
    assert result["real_consecutive_days"] == 9
    assert result["dates"][-1] == "2026-09-29"
    assert result["status"] == "IN_PROGRESS"
    assert result["rules"]["backfill"] is False
    assert result["rules"]["synthetic_days"] is False
    assert result["rules"]["real_money"] == "BLOCKED"


def test_cor11_rejects_gap():
    with pytest.raises(ValueError, match="COR11_NON_CONSECUTIVE_DATE"):
        advance(_ledger(), target=date(2026, 9, 30), evidence=_evidence("2026-09-30"))


def test_cor11_rejects_evidence_date_mismatch():
    with pytest.raises(ValueError, match="COR11_EVIDENCE_DATE_MISMATCH"):
        advance(_ledger(), target=date(2026, 9, 29), evidence=_evidence("2026-09-30"))


def test_cor11_emits_closure_only_at_14_real_days(tmp_path):
    ledger = _ledger()
    current = ledger
    for offset, day in enumerate(range(29, 35), start=1):
        target = date(2026, 9, day) if day <= 30 else date(2026, 10, day - 30)
        evidence = _evidence(target.isoformat())
        current = advance(current, target=target, evidence=evidence)
    assert current["real_consecutive_days"] == 14
    assert current["status"] == "RESOLVED"
    persist(tmp_path, current, target=date(2026, 10, 4))
    closure = tmp_path / "MATRIX_COR11_CLOSURE_EVIDENCE.json"
    assert closure.is_file()
    assert "ACCEPTANCE_EVIDENCE_SATISFIED" in closure.read_text(encoding="utf-8")
