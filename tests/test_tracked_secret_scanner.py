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


def _track(
    root,
    relative,
    content,
    *,
    encoding="utf-8",
):
    path = root / relative
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        content,
        encoding=encoding,
    )

    subprocess.run(
        ["git", "add", relative.as_posix()],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_scanner_detects_tracked_private_key(tmp_path):
    _init_repo(tmp_path)

    body = "A" * 120
    _track(
        tmp_path,
        __import__("pathlib").Path("bad.pem"),
        (
            "-----BEGIN PRIVATE KEY-----\n"
            + body
            + "\n-----END PRIVATE KEY-----\n"
        ),
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False


def test_scanner_detects_forbidden_tracked_name(tmp_path):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        __import__("pathlib").Path(".env"),
        "SAFE_PLACEHOLDER=1\n",
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


def test_scanner_detects_real_python_assignment(tmp_path):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        __import__("pathlib").Path("config.py"),
        'API_KEY = "live_1234567890abcdef"\n',
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False


def test_scanner_detects_sensitive_dict_literal(tmp_path):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        __import__("pathlib").Path("config.py"),
        (
            'CONFIG = {'
            '"client_secret": '
            '"live_1234567890abcdef"'
            '}\n'
        ),
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False


def test_test_fixture_generic_secret_literal_is_allowed(
    tmp_path,
):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        __import__("pathlib").Path(
            "tests/test_fixture.py"
        ),
        (
            'payload = {'
            '"client_secret": '
            '"synthetic-fixture-value"'
            '}\n'
        ),
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is True


def test_test_fixture_high_confidence_key_is_still_blocked(
    tmp_path,
):
    _init_repo(tmp_path)

    # Constructed to avoid embedding a real credential in this test.
    fake_high_confidence = (
        "AKIA"
        + "A" * 16
    )

    _track(
        tmp_path,
        __import__("pathlib").Path(
            "tests/test_fixture.py"
        ),
        (
            "value = "
            + repr(fake_high_confidence)
            + "\n"
        ),
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is False


def test_utf8_bom_fixture_is_parsed_safely(
    tmp_path,
):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        __import__("pathlib").Path(
            "tests/test_fixture.py"
        ),
        (
            'payload = {'
            '"api_key": '
            '"synthetic-fixture-value"'
            '}\n'
        ),
        encoding="utf-8-sig",
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(".env",),
    )

    assert report.ok is True


def test_scanner_ignores_binary_files(tmp_path):
    _init_repo(tmp_path)

    path = tmp_path / "blob.bin"
    path.write_bytes(
        b"\x00\x01\x02PRIVATE KEY"
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
