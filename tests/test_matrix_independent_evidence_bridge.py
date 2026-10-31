import hashlib
import json
from datetime import datetime, timedelta, timezone

from tools.matrix_independent_evidence_bridge import verify_bundle


def fixture(tmp_path):
    now = datetime(2026, 10, 30, 20, tzinfo=timezone.utc)
    quote = {"fixture_id": "123", "source": "BETANO", "verified": True}
    source = {"fixture_id": "123", "source": "SOFASCORE", "verified": True}
    sharp = {"fixture_id": "123", "source": "PINNACLE", "verified": True}
    captures = {}
    for name, data in (("fixture", source), ("quote", quote), ("sharp", sharp)):
        path = tmp_path / "evidence" / (name + ".json")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        captures[name] = {"path": "evidence/" + name + ".json", "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "source": data["source"]}
    readiness = {
        "discovery": {"source_order": ["SOFASCORE", "FLASHSCORE"], "fixture_verified": True, "evidence_path": captures["fixture"]["path"]},
        "quote": {"verified": True, "evidence_path": captures["quote"]["path"], "colombia_authorized": True, "market": "TOTAL_GOALS_OVER_UNDER", "selection": "OVER_2_5", "fixture_id": "123", "bookmaker": "BETANO", "decimal_odds": 1.9, "p_matrix": 0.65, "kickoff_utc": (now + timedelta(hours=1)).isoformat(), "updated_at_utc": now.isoformat()},
        "sharp": {"verified": True, "evidence_path": captures["sharp"]["path"], "fixture_id": "123", "updated_at_utc": now.isoformat()},
        "governance_pass": True, "correlation_pass": True,
    }
    return now, {"captures": captures, "readiness": readiness}


def test_integrity_bridge_is_shadow_only(tmp_path):
    now, bundle = fixture(tmp_path)
    result = verify_bundle(bundle, tmp_path, now)
    assert result["status"] == "SHADOW_READINESS_ONLY"
    assert result["telegram_calls"] == result["paid_api_calls"] == result["independent_api_calls"] == 0
    assert result["telegram_delivery_certified"] is False
    assert result["real_money"] == "BLOCKED"


def test_modified_capture_is_blocked(tmp_path):
    now, bundle = fixture(tmp_path)
    (tmp_path / "evidence" / "quote.json").write_text('{"changed":true}', encoding="utf-8")
    result = verify_bundle(bundle, tmp_path, now)
    assert result["status"] == "BLOCKED"
    assert any("DIGEST_MISMATCH" in x for x in result["blockers"])


def test_expired_provider_is_blocked(tmp_path):
    now, bundle = fixture(tmp_path)
    bundle["captures"]["quote"]["source"] = "API_FOOTBALL"
    result = verify_bundle(bundle, tmp_path, now)
    assert result["status"] == "BLOCKED"
    assert "EXPIRED_PROVIDER_NOT_ALLOWED" in result["blockers"]


def test_path_traversal_is_blocked(tmp_path):
    now, bundle = fixture(tmp_path)
    bundle["captures"]["quote"]["path"] = "evidence/../../secret.json"
    result = verify_bundle(bundle, tmp_path, now)
    assert result["status"] == "BLOCKED"
    assert any("PATH_INVALID" in x for x in result["blockers"])
