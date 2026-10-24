import json
from pathlib import Path


def test_cor11_real_day_sequence_20261002():
    p = Path('evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_20261002.json')
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['real_consecutive_days'] == 12
    assert d['target_days'] == 14
    assert d['dates'] == [
        '2026-09-21','2026-09-22','2026-09-23','2026-09-24',
        '2026-09-25','2026-09-26','2026-09-27','2026-09-28',
        '2026-09-29','2026-09-30','2026-10-01','2026-10-02'
    ]
    assert d['rules']['utc_rollover_used'] is False
    assert d['rules']['backfill'] is False
    assert d['rules']['synthetic_days'] is False
    assert d['rules']['real_money'] == 'BLOCKED'
    assert d['status'] == 'IN_PROGRESS'
