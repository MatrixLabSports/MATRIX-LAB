from pathlib import Path
import subprocess

from app.core.tracked_secret_scanner import (
    scan_tracked_repository,
)


def _init_repo(tmp_path):
    subprocess.run(
        ["git", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )


def test_scanner_detects_tracked_private_key(tmp_path):
    _init_repo(tmp_path)

    marker = (
        "-----BEGIN "
        + "PRIVATE KEY-----"
    )
    file_path = tmp_path / "bad.pem"
    file_path.write_text(
        marker + "\nabc\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "add", "bad.pem"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False
    assert report.scanned_files == 1
    assert any(
        finding.rule == "PRIVATE_KEY_MATERIAL"
        for finding in report.findings
    )


def test_scanner_detects_forbidden_tracked_name(tmp_path):
    _init_repo(tmp_path)

    file_path = tmp_path / ".env"
    file_path.write_text(
        "SAFE_PLACEHOLDER=1\n",
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "add", ".env"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False
    assert any(
        finding.rule
        == "FORBIDDEN_TRACKED_NAME"
        for finding in report.findings
    )


def test_scanner_detects_likely_embedded_secret(tmp_path):
    _init_repo(tmp_path)

    file_path = tmp_path / "config.py"
    file_path.write_text(
        'API_KEY = "live_1234567890abcdef"\n',
        encoding="utf-8",
    )

    subprocess.run(
        ["git", "add", "config.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False
    assert any(
        finding.rule
        == "LIKELY_EMBEDDED_SECRET"
        for finding in report.findings
    )


def test_scanner_ignores_binary_files(tmp_path):
    _init_repo(tmp_path)

    file_path = tmp_path / "blob.bin"
    file_path.write_bytes(
        b"\x00\x01\x02"
        + b"PRIVATE KEY"
    )

    subprocess.run(
        ["git", "add", "blob.bin"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is True
    assert report.scanned_files == 0
