from datetime import datetime, timezone
import json

import pytest

from app.core.evidence_writer import write_json_evidence


def test_evidence_writer_is_atomic_utf8_and_timestamped(tmp_path):
    path = write_json_evidence(
        tmp_path,
        prefix="gate",
        payload={"passed": True, "team": "Grobiņa"},
        observed_at_utc=datetime(2026, 8, 18, 10, 30, tzinfo=timezone.utc),
    )
    assert path.name == "gate_20260818T103000Z.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["team"] == "Grobiņa"
    assert payload["evidence_written_at_utc"].endswith("+00:00")
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize("key", ["password", "api_key", "database_url", "authorization", "access_token"])
def test_evidence_writer_rejects_credential_bearing_keys_recursively(tmp_path, key):
    with pytest.raises(ValueError, match="forbidden key"):
        write_json_evidence(tmp_path, prefix="gate", payload={"nested": {key: "sensitive"}})


def test_evidence_writer_requires_true_utc(tmp_path):
    from datetime import timedelta, timezone as tz

    with pytest.raises(ValueError, match="UTC"):
        write_json_evidence(
            tmp_path,
            prefix="gate",
            payload={"passed": True},
            observed_at_utc=datetime(2026, 8, 18, 5, 30, tzinfo=tz(timedelta(hours=-5))),
        )


def test_evidence_writer_creates_verifiable_sha256_sidecar_and_detects_tampering(tmp_path):
    from app.core.evidence_writer import evidence_sha256_path, verify_evidence_sha256

    path = write_json_evidence(
        tmp_path,
        prefix="gate",
        payload={"passed": True},
        observed_at_utc=datetime(2026, 8, 18, 10, 30, tzinfo=timezone.utc),
    )
    sidecar = evidence_sha256_path(path)
    assert sidecar.is_file()
    assert verify_evidence_sha256(path) is True

    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    assert verify_evidence_sha256(path) is False
