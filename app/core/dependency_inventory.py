from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import tomllib
from typing import Any, Mapping


_REQ_NAME = re.compile(
    r"^\s*([A-Za-z0-9_.-]+)"
)

_INCLUDE = re.compile(
    r"^(?:-r|--requirement)\s+(.+)$"
)

_CONSTRAINT = re.compile(
    r"^(?:-c|--constraint)\s+(.+)$"
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _sha(value: Any) -> str:
    return sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _normalize_requirement(
    value: str,
) -> str:
    return " ".join(
        value.strip().split()
    )


def _dependency_name(
    declaration: str,
) -> str | None:
    match = _REQ_NAME.match(
        declaration
    )

    if match is None:
        return None

    return match.group(1).lower()


@dataclass(frozen=True)
class DependencyInventory:
    source_files: tuple[str, ...]
    source_file_sha256: tuple[
        tuple[str, str],
        ...
    ]
    declared_requirements: tuple[str, ...]
    declared_dependencies: tuple[str, ...]
    inventory_fingerprint: str

    def payload(self) -> Mapping[str, Any]:
        return {
            "schema": "matrix.dependency-inventory/3",
            "source_files": list(
                self.source_files
            ),
            "source_file_sha256": [
                {
                    "path": path,
                    "sha256": digest,
                }
                for path, digest
                in self.source_file_sha256
            ],
            "declared_requirements": list(
                self.declared_requirements
            ),
            "declared_dependencies": list(
                self.declared_dependencies
            ),
            "recursive_requirement_includes_followed": True,
            "runtime_environment_not_authoritative": True,
            "automatic_dependency_upgrade": False,
            "inventory_fingerprint": (
                self.inventory_fingerprint
            ),
        }


def _safe_child(
    root: Path,
    parent: Path,
    raw_value: str,
) -> Path:
    raw = raw_value.strip().strip(
        "\"'"
    )

    if (
        "://" in raw
        or raw.startswith(
            ("git+", "http:", "https:")
        )
    ):
        raise ValueError(
            "REMOTE_REQUIREMENT_INCLUDE_NOT_ALLOWED"
        )

    child = (
        parent.parent / raw
    ).resolve()

    try:
        child.relative_to(root)
    except ValueError as error:
        raise ValueError(
            "REQUIREMENT_INCLUDE_ESCAPES_REPOSITORY"
        ) from error

    return child


def _walk_requirements(
    *,
    root: Path,
    path: Path,
    visiting: set[Path],
    visited: set[Path],
    declarations: list[str],
    sources: dict[str, str],
) -> None:
    path = path.resolve()

    if path in visiting:
        raise ValueError(
            "REQUIREMENT_INCLUDE_CYCLE"
        )

    if path in visited:
        return

    if not path.is_file():
        raise ValueError(
            "REQUIREMENT_INCLUDE_NOT_FOUND"
        )

    visiting.add(path)

    relative = path.relative_to(
        root
    ).as_posix()
    sources[relative] = sha256(
        path.read_bytes()
    ).hexdigest()

    for raw_line in path.read_text(
        encoding="utf-8-sig",
    ).splitlines():
        line = raw_line.strip()

        if (
            not line
            or line.startswith("#")
        ):
            continue

        include = _INCLUDE.match(
            line
        )
        constraint = _CONSTRAINT.match(
            line
        )

        if include or constraint:
            raw_child = (
                include.group(1)
                if include
                else constraint.group(1)
            )

            child = _safe_child(
                root,
                path,
                raw_child,
            )

            _walk_requirements(
                root=root,
                path=child,
                visiting=visiting,
                visited=visited,
                declarations=declarations,
                sources=sources,
            )
            continue

        if line.startswith("-"):
            continue

        declarations.append(
            _normalize_requirement(
                line
            )
        )

    visiting.remove(path)
    visited.add(path)


def _read_pyproject(
    path: Path,
) -> list[str]:
    data = tomllib.loads(
        path.read_text(
            encoding="utf-8-sig",
        )
    )

    result: list[str] = []

    project = data.get(
        "project",
        {},
    )

    for item in project.get(
        "dependencies",
        [],
    ):
        if isinstance(item, str):
            result.append(
                _normalize_requirement(
                    item
                )
            )

    optional = project.get(
        "optional-dependencies",
        {},
    )

    if isinstance(optional, dict):
        for values in optional.values():
            if isinstance(values, list):
                for item in values:
                    if isinstance(item, str):
                        result.append(
                            _normalize_requirement(
                                item
                            )
                        )

    build_system = data.get(
        "build-system",
        {},
    )

    for item in build_system.get(
        "requires",
        [],
    ):
        if isinstance(item, str):
            result.append(
                _normalize_requirement(
                    item
                )
            )

    return result


def build_dependency_inventory(
    root: str | Path,
) -> DependencyInventory:
    root_path = Path(root).resolve()
    declarations: list[str] = []
    sources: dict[str, str] = {}
    visited: set[Path] = set()

    for name in (
        "requirements.txt",
        "requirements-dev.txt",
        "requirements-test.txt",
    ):
        path = root_path / name

        if not path.exists():
            continue

        _walk_requirements(
            root=root_path,
            path=path,
            visiting=set(),
            visited=visited,
            declarations=declarations,
            sources=sources,
        )

    pyproject = root_path / "pyproject.toml"

    if pyproject.exists():
        sources[
            "pyproject.toml"
        ] = sha256(
            pyproject.read_bytes()
        ).hexdigest()

        declarations.extend(
            _read_pyproject(
                pyproject
            )
        )

    source_tuple = tuple(
        sorted(sources)
    )
    hash_tuple = tuple(
        sorted(
            sources.items()
        )
    )
    requirement_tuple = tuple(
        sorted(
            set(declarations)
        )
    )

    dependencies = tuple(
        sorted(
            {
                name
                for declaration
                in requirement_tuple
                if (
                    name
                    := _dependency_name(
                        declaration
                    )
                )
                is not None
            }
        )
    )

    base = {
        "schema": "matrix.dependency-inventory/3",
        "source_files": list(
            source_tuple
        ),
        "source_file_sha256": [
            {
                "path": path,
                "sha256": digest,
            }
            for path, digest
            in hash_tuple
        ],
        "declared_requirements": list(
            requirement_tuple
        ),
        "declared_dependencies": list(
            dependencies
        ),
        "recursive_requirement_includes_followed": True,
        "runtime_environment_not_authoritative": True,
        "automatic_dependency_upgrade": False,
    }

    return DependencyInventory(
        source_files=source_tuple,
        source_file_sha256=hash_tuple,
        declared_requirements=(
            requirement_tuple
        ),
        declared_dependencies=(
            dependencies
        ),
        inventory_fingerprint=_sha(
            base
        ),
    )
