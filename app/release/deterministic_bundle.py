from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import os
import zipfile

from .canonical import file_sha256

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_DEFAULT_EXCLUDES = {".pytest_cache", "__pycache__", ".git"}


@dataclass(frozen=True)
class BundleResult:
    path: Path
    sha256: str
    file_count: int


def _safe_relative(path: Path, root: Path) -> str:
    relative = path.relative_to(root).as_posix()
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or relative in ("", "."):
        raise ValueError(f"unsafe bundle path: {relative}")
    return relative


def _collect_files(root: Path) -> list[tuple[str, Path]]:
    if not root.exists() or not root.is_dir():
        raise ValueError("bundle root must be an existing directory")
    files: list[tuple[str, Path]] = []
    for current_root, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(current_root)
        dirnames[:] = sorted(name for name in dirnames if name not in _DEFAULT_EXCLUDES)
        for dirname in tuple(dirnames):
            candidate = current / dirname
            if candidate.is_symlink():
                raise ValueError(f"symlink directory forbidden in bundle: {candidate}")
        for filename in sorted(filenames):
            path = current / filename
            if any(part in _DEFAULT_EXCLUDES for part in path.relative_to(root).parts):
                continue
            if path.is_symlink():
                raise ValueError(f"symlink file forbidden in bundle: {path}")
            if not path.is_file():
                raise ValueError(f"non-regular file forbidden in bundle: {path}")
            files.append((_safe_relative(path, root), path))
    files.sort(key=lambda item: item[0])
    seen: set[str] = set()
    for relative, _ in files:
        folded = relative.casefold()
        if folded in seen:
            raise ValueError(f"case-insensitive duplicate bundle path: {relative}")
        seen.add(folded)
    return files


def build_deterministic_zip(root: str | Path, destination: str | Path) -> BundleResult:
    root_path = Path(root).resolve()
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    files = _collect_files(root_path)
    if not files:
        raise ValueError("refusing to build an empty release bundle")
    temp_path = destination_path.with_suffix(destination_path.suffix + ".tmp")
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for relative, path in files:
                info = zipfile.ZipInfo(relative, date_time=_FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.create_system = 3
                data = path.read_bytes()
                archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temp_path, destination_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return BundleResult(destination_path, file_sha256(destination_path), len(files))
