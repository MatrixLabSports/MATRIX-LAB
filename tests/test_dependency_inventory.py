from app.core.dependency_inventory import (
    build_dependency_inventory,
)


def test_dependency_inventory_is_deterministic_and_version_bound(
    tmp_path,
):
    path = (
        tmp_path
        / "requirements.txt"
    )
    path.write_text(
        "pytest==8.3.0\nrequests>=2.0\n",
        encoding="utf-8",
    )

    first = build_dependency_inventory(
        tmp_path
    )
    second = build_dependency_inventory(
        tmp_path
    )

    assert first == second
    assert first.declared_dependencies == (
        "pytest",
        "requests",
    )
    assert "pytest==8.3.0" in (
        first.declared_requirements
    )
    assert (
        first.payload()[
            "automatic_dependency_upgrade"
        ]
        is False
    )

    path.write_text(
        "pytest==8.4.0\nrequests>=2.0\n",
        encoding="utf-8",
    )

    changed = build_dependency_inventory(
        tmp_path
    )

    assert (
        changed.inventory_fingerprint
        != first.inventory_fingerprint
    )


def test_pyproject_dependencies_are_inventoried(
    tmp_path,
):
    (
        tmp_path
        / "pyproject.toml"
    ).write_text(
        """
[project]
name = "matrix-test"
version = "0.0.1"
dependencies = [
    "numpy>=2.0",
]

[project.optional-dependencies]
test = [
    "pytest>=8",
]
""".strip()
        + "\n",
        encoding="utf-8",
    )

    inventory = (
        build_dependency_inventory(
            tmp_path
        )
    )

    assert inventory.declared_dependencies == (
        "numpy",
        "pytest",
    )
