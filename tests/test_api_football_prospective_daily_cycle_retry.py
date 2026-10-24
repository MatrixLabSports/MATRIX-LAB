from pathlib import Path

import pytest

import tools.api_football_prospective_daily_cycle as daily


def _manifest():
    return {
        "fixtures_received": 4,
        "eligible_future_fixtures": 2,
        "response_sha256": "abc",
    }


def test_fixture_capture_retries_transient_provider_errors(monkeypatch, tmp_path):
    calls=[]
    def fake_capture(**kwargs):
        calls.append(kwargs["out_dir"].name)
        if len(calls) < 3:
            raise ValueError("API_FOOTBALL_PROVIDER_ERRORS")
        out=kwargs["out_dir"]
        out.mkdir(parents=True, exist_ok=True)
        (out/"future_fixture_registry.json").write_text('{"events":[]}\n')
        (out/"capture_manifest.json").write_text("{}\n")
        return _manifest()
    monkeypatch.setattr(daily, "capture_future_fixtures", fake_capture)
    sleeps=[]
    manifest,recovery=daily._capture_fixtures_with_retry(
        api_key="k",
        out_dir=tmp_path,
        target_date="2026-10-24",
        captured_at_utc="2026-10-24T10:00:00+00:00",
        sleep_fn=sleeps.append,
    )
    assert manifest["eligible_future_fixtures"]==2
    assert calls==["attempt_1","attempt_2","attempt_3"]
    assert sleeps==[2,5]
    assert recovery["status"]=="PASS_AFTER_RETRY"
    assert recovery["successful_attempt"]==3
    assert (tmp_path/"provider_recovery.json").exists()
    assert (tmp_path/"future_fixture_registry.json").exists()


def test_fixture_capture_stops_on_nonrecoverable_error(monkeypatch, tmp_path):
    calls=[]
    def fake_capture(**kwargs):
        calls.append(1)
        raise ValueError("TARGET_DATE_INVALID")
    monkeypatch.setattr(daily, "capture_future_fixtures", fake_capture)
    with pytest.raises(ValueError, match="API_FOOTBALL_FIXTURE_CAPTURE_EXHAUSTED"):
        daily._capture_fixtures_with_retry(
            api_key="k",
            out_dir=tmp_path,
            target_date="bad",
            captured_at_utc="2026-10-24T10:00:00+00:00",
            sleep_fn=lambda _: None,
        )
    assert len(calls)==1
    text=(tmp_path/"provider_recovery.json").read_text()
    assert "PROVIDER_BLOCKED_AFTER_RETRIES" in text
    assert "TARGET_DATE_INVALID" in text


def test_fixture_capture_exhausts_three_recoverable_attempts(monkeypatch, tmp_path):
    calls=[]
    def fake_capture(**kwargs):
        calls.append(1)
        raise ValueError("API_FOOTBALL_PROVIDER_ERRORS")
    monkeypatch.setattr(daily, "capture_future_fixtures", fake_capture)
    with pytest.raises(ValueError, match="API_FOOTBALL_FIXTURE_CAPTURE_EXHAUSTED"):
        daily._capture_fixtures_with_retry(
            api_key="k",
            out_dir=tmp_path,
            target_date="2026-10-24",
            captured_at_utc="2026-10-24T10:00:00+00:00",
            sleep_fn=lambda _: None,
        )
    assert len(calls)==3
    text=(tmp_path/"provider_recovery.json").read_text()
    assert text.count('"status": "FAIL"')==3


def test_fixture_capture_does_not_retry_terminal_daily_limit(monkeypatch, tmp_path):
    calls=[]
    def fake_capture(**kwargs):
        calls.append(1)
        raise ValueError("API_FOOTBALL_DAILY_REQUEST_LIMIT_REACHED")
    monkeypatch.setattr(daily, "capture_future_fixtures", fake_capture)
    with pytest.raises(ValueError, match="API_FOOTBALL_FIXTURE_CAPTURE_EXHAUSTED"):
        daily._capture_fixtures_with_retry(
            api_key="k",
            out_dir=tmp_path,
            target_date="2026-10-24",
            captured_at_utc="2026-10-24T10:00:00+00:00",
            sleep_fn=lambda _: None,
        )
    assert len(calls)==1
    data=(tmp_path/"provider_recovery.json").read_text()
    assert '"terminal_for_current_cycle": true' in data
    assert "API_FOOTBALL_DAILY_REQUEST_LIMIT_REACHED" in data
