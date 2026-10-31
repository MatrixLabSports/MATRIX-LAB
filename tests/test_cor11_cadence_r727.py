import json
from pathlib import Path


def test_cor11_r727_real_day_sequence():
    p = Path('evidence/cor11/MATRIX_COR11_CADENCE_LEDGER_R727.json')
    d = json.loads(p.read_text(encoding='utf-8'))
    assert d['real_consecutive_days'] == 8
    assert d['target_days'] == 14
    assert d['dates'] == [f'2026-09-{day:02d}' for day in range(21, 29)]
    assert d['rules']['utc_rollover_used'] is False
    assert d['rules']['backfill'] is False
    assert d['rules']['synthetic_days'] is False
