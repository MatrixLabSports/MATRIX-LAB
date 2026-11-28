"""Physical collector entry test with an inert, pre-opened authorized tab.

No network, no actual wager, no synthetic bookmaker odds, no signal.
The test proves a 5m cycle never opens new bookmaker pages without a
certified in-window original or research-only event target.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import tools.matrix_early_research_quote_intake as research
import tools.matrix_selfhosted_browser_quote_collector as collector


class ExistingBookPage:
    url = "https://www.betano.co/"
    def is_closed(self):
        return False
    def title(self):
        return "Betano · existing browser tab"
    def locator(self, key):
        assert key == "body"
        return SimpleNamespace(inner_text=lambda timeout: "Betano rendered page without matched fixtures")


class Context:
    def __init__(self):
        self.pages = [ExistingBookPage()]
        self.open_attempts = 0
    def new_page(self):
        self.open_attempts += 1
        raise AssertionError("EMPTY_CANDIDATE_CYCLE_MUST_NOT_OPEN_BOOKMAKER_TAB")


class FakePlaywright:
    def __init__(self, context):
        self.context = context
    def __enter__(self):
        self.chromium = SimpleNamespace(
            connect_over_cdp=lambda endpoint, timeout: SimpleNamespace(
                contexts=[self.context]
            )
        )
        return self
    def __exit__(self, *args):
        return False


def test_empty_candidate_cycle_reads_existing_tab_without_opening_new_sites(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    audit = tmp_path / "audit.json"
    adapters = tmp_path / "adapters.json"
    output = tmp_path / "collection.json"
    raw_dir = tmp_path / "browser_cdp"
    config.write_text(json.dumps({"browser":{"default_cdp_endpoint":"http://127.0.0.1:9222"}}))
    audit.write_text(json.dumps({"generated_at_utc":datetime.now(timezone.utc).isoformat(),
                                 "records":[],"browser_prematch_candidate_rows":[]}))
    adapters.write_text(json.dumps({"bookmakers":{
        "betano":{"entry_url":"https://www.betano.co/","status":"CERTIFIED_EXACT_OVER25"},
        "bwin":{"entry_url":"https://www.bwin.co/","status":"RESEARCH_ONLY"},
        "betplay":{"entry_url":"https://www.betplay.com.co/","status":"RESEARCH_ONLY"},
    }}))
    ctx = Context()
    monkeypatch.setattr(collector,"ROOT",tmp_path)
    monkeypatch.setattr(collector,"CONFIG",config)
    monkeypatch.setattr(collector,"AUDIT",audit)
    monkeypatch.setattr(collector,"ADAPTERS",adapters)
    monkeypatch.setattr(collector,"OUT",output)
    monkeypatch.setattr(collector,"RAW_ROOT",raw_dir)
    monkeypatch.setattr(collector,"synchronized_governed_candidate_rows",lambda now:[])
    monkeypatch.setattr(collector,"independent_research_quote_targets",lambda now:[])
    monkeypatch.setattr(collector,"candidate_pipeline_diagnostic",lambda audit,now:{})
    monkeypatch.setattr(research,"early_targets",lambda now,root:[])
    monkeypatch.setattr(collector,"sync_playwright",lambda:FakePlaywright(ctx))
    collector.main()
    result=json.loads(output.read_text(encoding="utf-8"))
    assert ctx.open_attempts == 0
    assert result["candidate_count_in_final_window"] == 0
    assert result["research_only_quote_target_count"] == 0
    assert result["authorized_book_pages_captured"] == 1
    assert result["betano_exact_quote_count"] == 0
    assert result["status"] == "NO_ELIGIBLE_PREMATCH_TARGETS"
    assert result["target_scope_diagnostic"]["new_bookmaker_page_opening_allowed"] is False
    assert result["policy"]["automatic_wagering"] is False
    assert result["policy"]["real_money"] == "BLOCKED"
    assert not list(raw_dir.glob("*.txt"))  # No unrelated rendered page data persisted
