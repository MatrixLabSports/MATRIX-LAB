import json
from pathlib import Path
from tools.matrix_browser_quote_recovery_queue import main

def test_browser_recovery_queue_builds_failover():
    main()
    out=json.loads(Path("evidence/notifications/telegram/MATRIX_BROWSER_QUOTE_RECOVERY_QUEUE_LAST.json").read_text(encoding="utf-8"))
    assert out["policy"]["never_wait_for_exhausted_provider"] is True
    assert out["policy"]["switch_to_browser_recovery_immediately"] is True
    assert out["policy"]["automatic_wagering"] is False
    assert all(x["required_market"]=="OVER_2_5" for x in out["queue"])
