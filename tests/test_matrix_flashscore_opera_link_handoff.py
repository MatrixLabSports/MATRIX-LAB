"""Flashscore accessibility link intake cannot manufacture per-event clock."""
import json
from datetime import datetime, timedelta, timezone
from tools.matrix_flashscore_opera_link_handoff import scan, page_label

DAY = "2026-11-05"
NOW = datetime(2026, 11, 5, 9, 0, tzinfo=timezone.utc)
URL = "https://www.flashscore.co/partido/futbol/ac-milan-8Sa8HInO/ferencvaros-pKS9M7R7/?mid=hUC4nhiT"


def item():
    return {"schema": "MATRIX_OPERA_FLASHSCORE_FOOTBALL_LINK_CAPTURE_V1",
            "source": "FLASHSCORE",
            "source_page_url": "https://www.flashscore.co/",
            "source_order": ["SOFASCORE", "FLASHSCORE", "APIS"],
            "target_date_bogota": DAY,
            "visible_date_selector": "jueves, 5 de noviembre de 2026",
            "observed_at_utc": "2026-11-05T08:55:00+00:00",
            "capture_method": "OPERA_CONNECTOR_ACCESSIBILITY_LINKS",
            "links": [{"name": "AC Milan - Ferencvaros", "url": URL}],
            "record_count": 1,
            "signal_generation_authorized": False,
            "automatic_wagering": False,
            "real_money": "BLOCKED"}


def write(tmp_path, data):
    path = (tmp_path / "evidence/browser_capture_inbox/opera_football_flash" /
            DAY / "20261105T085500Z.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_exact_visible_flashscore_links_are_discovery_only(tmp_path):
    write(tmp_path, item())
    r = scan(tmp_path, DAY, now=NOW)
    assert r["status"] == "FLASH_OPERA_LINKS_RESEARCH_ONLY_EVENT_DATE_UNVERIFIED"
    assert r["valid_mid_link_count"] == 1
    assert r["links"][0]["mid"] == "hUC4nhiT"
    assert r["individual_event_date_verified"] is False
    assert r["individual_event_utc_kickoff_verified"] is False
    assert r["sofa_flash_crosswalk_verified"] is False
    assert r["production_probability_authorized"] is False
    assert r["telegram_signal_authorized"] is False
    assert len(r["source_sha256"]) == 64


def test_bad_calendar_date_selector_cannot_admit_links(tmp_path):
    d = item()
    d["visible_date_selector"] = "viernes, 6 de noviembre de 2026"
    write(tmp_path, d)
    r = scan(tmp_path, DAY, now=NOW)
    assert r["valid_mid_link_count"] == 0
    assert r["snapshots_rejected"] == 1
    assert page_label(DAY) == "jueves, 5 de noviembre de 2026"


def test_absent_mid_or_unsafe_domain_never_becomes_event(tmp_path):
    d = item()
    d["links"] = [{"url": "https://evil.example/partido/futbol/a/b/?mid=hUC4nhiT",
                   "name": "AC Milan - Ferencvaros"},
                  {"url": URL.replace("?mid=", "?notmid="),
                   "name": "AC Milan - Ferencvaros"}]
    d["record_count"] = 2
    write(tmp_path, d)
    r = scan(tmp_path, DAY, now=NOW)
    assert r["valid_mid_link_count"] == 0


def test_cli_persists_valid_json_with_real_newline(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    import sys
    from tools.matrix_flashscore_opera_link_handoff import main
    d = item()
    d["observed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write(tmp_path, d)
    output = (tmp_path / "evidence" / "football_world_inventory" /
              DAY / "MATRIX_FLASH_OPERA_LINK_ONLY_HANDOFF_LAST.json")
    monkeypatch.setattr(sys,"argv",["flash_link_handoff","--day",DAY,
                                   "--root",str(tmp_path),"--out",str(output)])
    main()
    content = output.read_text(encoding="utf-8")
    assert content.endswith("\\n")
    assert not content.endswith("\\\\n")
    assert json.loads(content)["valid_mid_link_count"] == 1


def test_stale_and_future_flashscore_capture_are_not_replayed(tmp_path):
    d = item()
    d["observed_at_utc"] = "2026-11-04T07:00:00+00:00"
    path = write(tmp_path, d)
    assert scan(tmp_path, DAY, now=NOW)["valid_mid_link_count"] == 0
    d["observed_at_utc"] = "2026-11-05T09:01:00+00:00"
    path.write_text(json.dumps(d), encoding="utf-8")
    assert scan(tmp_path, DAY, now=NOW)["valid_mid_link_count"] == 0
