from app.core.dependency_inventory import (
    build_dependency_inventory,
)


def test_recursive_requirement_include_is_bound(
    tmp_path,
):
    (
        tmp_path
        / "requirements.txt"
    ).write_text(
        "-r requirements-base.txt\n",
        encoding="utf-8",
    )
    (
        tmp_path
        / "requirements-base.txt"
    ).write_text(
        "requests==2.32.0\n",
        encoding="utf-8",
    )

    inventory = (
        build_dependency_inventory(
            tmp_path
        )
    )

    assert inventory.source_files == (
        "requirements-base.txt",
        "requirements.txt",
    )
    assert (
        "requests==2.32.0"
        in inventory.declared_requirements
    )


def test_requirement_include_cycle_fails_closed(
    tmp_path,
):
    (
        tmp_path
        / "requirements.txt"
    ).write_text(
        "-r other.txt\n",
        encoding="utf-8",
    )
    (
        tmp_path
        / "other.txt"
    ).write_text(
        "-r requirements.txt\n",
        encoding="utf-8",
    )

    try:
        build_dependency_inventory(
            tmp_path
        )
    except ValueError as error:
        assert str(error) == (
            "REQUIREMENT_INCLUDE_CYCLE"
        )
    else:
        raise AssertionError(
            "cycle must fail closed"
        )


def test_version_change_changes_fingerprint(
    tmp_path,
):
    path = tmp_path / "requirements.txt"
    path.write_text(
        "pytest==8.3.0\n",
        encoding="utf-8",
    )

    first = build_dependency_inventory(
        tmp_path
    )

    path.write_text(
        "pytest==8.4.0\n",
        encoding="utf-8",
    )

    second = build_dependency_inventory(
        tmp_path
    )

    assert (
        first.inventory_fingerprint
        != second.inventory_fingerprint
    )
