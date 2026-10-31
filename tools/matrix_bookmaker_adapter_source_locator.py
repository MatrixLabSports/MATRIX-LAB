"""Find bookmaker-adapter code locations without reading or emitting credentials.

Read-only local source inventory. A matching file is a lead, not certification.
"""
from __future__ import annotations
import json
from pathlib import Path

TOKENS = ("BOOKMAKER_ADAPTER_NOT_CERTIFIED", "CAPTURE_ONLY_PENDING_SELECTOR_CERTIFICATION",
          "CERTIFIED_EXACT_OVER25", "betano_detail_resources_checked")
SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "node_modules", "evidence"}


def locate(root: Path) -> dict:
    found = {}
    for folder in ("tools", "tests", ".github"):
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any(part in SKIP for part in path.relative_to(root).parts):
                continue
            if path.suffix not in (".py", ".yml", ".yaml"):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                continue
            hits = [{"line": index, "token": token} for index, line in enumerate(lines, 1)
                    for token in TOKENS if token in line]
            if hits:
                found[path.relative_to(root).as_posix()] = hits
    return {"schema": "MATRIX_BOOKMAKER_ADAPTER_SOURCE_LOCATOR_V1",
            "source_matches": found, "adapter_certified": False,
            "provider_freshness_certified": False, "telegram_delivery_certified": False,
            "real_money": "BLOCKED", "automatic_wagering": False}


def main() -> None:
    print(json.dumps(locate(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
