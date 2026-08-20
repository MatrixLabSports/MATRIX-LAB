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
    name,
    content,
    *,
    encoding="utf-8",
):
    path = root / name
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        content,
        encoding=encoding,
    )
    subprocess.run(
        ["git", "add", name],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_env_operational_variant_is_forbidden(tmp_path):
    _init_repo(tmp_path)
    _track(
        tmp_path,
        ".env.production",
        "SAFE_PLACEHOLDER=1\n",
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(
            ".env",
            ".env.local",
        ),
    )

    assert report.ok is False
    assert any(
        item.rule
        == "FORBIDDEN_TRACKED_NAME"
        for item in report.findings
    )


def test_explicit_env_example_template_is_allowed(tmp_path):
    _init_repo(tmp_path)
    _track(
        tmp_path,
        ".env.example",
        "PROVIDER_API_KEY=\n",
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(
            ".env",
            ".env.local",
        ),
    )

    assert report.ok is True


def test_env_example_is_still_content_scanned(tmp_path):
    _init_repo(tmp_path)
    _track(
        tmp_path,
        ".env.example",
        (
            "API_KEY="
            "live_1234567890abcdef\n"
        ),
    )

    report = scan_tracked_repository(
        tmp_path,
        forbidden_names=(
            ".env",
            ".env.local",
        ),
    )

    assert report.ok is False
    assert any(
        item.rule
        == "LIKELY_EMBEDDED_SECRET"
        for item in report.findings
    )


def test_oversized_tracked_text_fails_closed(tmp_path):
    _init_repo(tmp_path)
    path = tmp_path / "large.txt"
    path.write_text(
        "A" * (2 * 1024 * 1024 + 1),
        encoding="utf-8",
    )
    subprocess.run(
        ["git", "add", "large.txt"],
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
        item.rule
        == "OVERSIZED_TEXT_NOT_SCANNED"
        for item in report.findings
    )


def test_generic_secret_outside_tests_is_blocked(tmp_path):
    _init_repo(tmp_path)
    _track(
        tmp_path,
        "config.py",
        (
            'API_KEY = '
            '"live_1234567890abcdef"\n'
        ),
    )

    assert (
        scan_tracked_repository(
            tmp_path,
            forbidden_names=(".env",),
        ).ok
        is False
    )


def test_synthetic_fixture_remains_allowed(tmp_path):
    _init_repo(tmp_path)
    _track(
        tmp_path,
        "tests/test_fixture.py",
        (
            'payload = {'
            '"client_secret": '
            '"synthetic-fixture-value"'
            '}\n'
        ),
    )

    assert (
        scan_tracked_repository(
            tmp_path,
            forbidden_names=(".env",),
        ).ok
        is True
    )


def test_high_confidence_credential_in_tests_is_blocked(
    tmp_path,
):
    _init_repo(tmp_path)

    high_confidence = (
        "AKIA"
        + "A" * 16
    )

    _track(
        tmp_path,
        "tests/test_fixture.py",
        (
            "value = "
            + repr(high_confidence)
            + "\n"
        ),
    )

    assert (
        scan_tracked_repository(
            tmp_path,
            forbidden_names=(".env",),
        ).ok
        is False
    )


def test_complete_pem_like_private_key_is_blocked(tmp_path):
    _init_repo(tmp_path)

    body = "A" * 120

    _track(
        tmp_path,
        "private.pem",
        (
            "-----BEGIN PRIVATE KEY-----\n"
            + body
            + "\n-----END PRIVATE KEY-----\n"
        ),
    )

    assert (
        scan_tracked_repository(
            tmp_path,
            forbidden_names=(".env",),
        ).ok
        is False
    )


def test_utf8_bom_fixture_is_handled_safely(tmp_path):
    _init_repo(tmp_path)

    _track(
        tmp_path,
        "tests/test_fixture.py",
        (
            'payload = {'
            '"api_key": '
            '"synthetic-fixture-value"'
            '}\n'
        ),
        encoding="utf-8-sig",
    )

    assert (
        scan_tracked_repository(
            tmp_path,
            forbidden_names=(".env",),
        ).ok
        is True
    )


def test_binary_files_are_not_text_scanned(tmp_path):
    _init_repo(tmp_path)

    path = tmp_path / "blob.bin"
    path.write_bytes(
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
