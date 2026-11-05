"""Restore missing/mismatched archived Over25 inputs ONLY via original SHA-256.

Sources can be recovered from captured provider day documents or exact copies
in sibling research archives. Re-serialization is allowed only when bytes hash
exactly to the immutable sealed forecast's original SHA. No forecasts, models,
governance or Telegram paths are ever written.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from tools.matrix_over25_source_hash_exact_repair import variants, MAX_BYTES
from tools.matrix_independent_over25_prematch_freeze import SCHEMA

ROOT = Path("evidence/football_research_freezes")
REPORT = Path("evidence/football_world_inventory/MATRIX_OVER25_MISSING_SOURCE_EXACT_RESTORE_LAST.json")
ORIGINALS = {"intake": "MATRIX_FOOTBALL_INDEPENDENT_FIXTURE_INTAKE.json",
             "shadow": "MATRIX_INDEPENDENT_OVER25_HISTORY_SHADOW.json"}

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def verified_variant(path: Path, expected: str) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        raw = path.read_bytes()
        if digest(raw) == expected:
            return raw
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            return None
        for _, data in variants(parsed):
            if digest(data) == expected:
                return data
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None
    return None

def capture_candidates(root: Path, folder: Path, label: str, expected: str):
    """Candidates are provider documents from the actual target day or near dates."""
    for sibling in sorted((root / ROOT).glob("20??-??-??/sources/" + expected + ".json")):
        if sibling != folder / "sources" / (expected + ".json"):
            yield sibling
    try:
        target = date.fromisoformat(folder.name)
    except ValueError:
        return
    for offset in (-2, -1, 0, 1):
        day = (target + timedelta(days=offset)).isoformat()
        yield root / "evidence/football_world_inventory" / day / ORIGINALS[label]

def recover(root: Path, *, write: bool) -> dict:
    root = root.resolve()
    base = root / ROOT
    # A SHA-named source file can legitimately serve more than one role.
    # Deduplicate by physical source path, retaining all legitimate origin roles.
    required: dict[str, tuple[Path, str, set[str]]] = {}
    failed: list[dict] = []
    for file in sorted(base.glob("20??-??-??/[0-9]*_*.json")):
        if "_result_" in file.name:
            continue
        try:
            forecast = json.loads(file.read_text(encoding="utf-8-sig"))
            if (forecast.get("schema") != SCHEMA
                or forecast.get("provider") != "FOOTBALL_DATA_ORG"
                or forecast.get("real_money") != "BLOCKED"
                or forecast.get("production_p_matrix_authorized") is not False
                or forecast.get("telegram_signal_authorized") is not False):
                raise ValueError("UNTRUSTED_FROZEN_FORECAST")
            for label in ORIGINALS:
                expected = forecast["source_" + label + "_file_sha256"]
                if (not isinstance(expected, str) or len(expected) != 64
                    or any(c not in "0123456789abcdef" for c in expected)):
                    raise ValueError("FORECAST_EXPECTED_SOURCE_HASH_INVALID")
                dest = file.parent / "sources" / (expected + ".json")
                key = dest.relative_to(root).as_posix()
                if key not in required:
                    required[key] = (dest, expected, set())
                required[key][2].add(label)
        except (ValueError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
            failed.append({"file": file.relative_to(root).as_posix(),
                           "reason": str(exc)[:120]})
    valid = 0
    restored = []
    blocked = []
    for dest, expected, labels in required.values():
        key = dest.relative_to(root).as_posix()
        # A reconstructible JSON object is NOT yet a valid archived source:
        # only on-disk bytes with the committed hash pass the existing check.
        if dest.is_file() and dest.stat().st_size <= MAX_BYTES and digest(dest.read_bytes()) == expected:
            valid += 1
            continue
        if dest.is_file() and dest.stat().st_size > MAX_BYTES:
            blocked.append({"path": key, "reason": "CORRUPT_SOURCE_OVERSIZED"})
            continue
        found = None
        origin = None
        from itertools import chain
        for candidate in chain((dest,), *(capture_candidates(root, dest.parent.parent, label, expected)
                                            for label in sorted(labels))):
            result = verified_variant(candidate, expected)
            if result is not None:
                found = result
                origin = candidate
                break
        if found is None:
            blocked.append({"path": key, "reason": "ORIGINAL_SHA_BYTES_NOT_PROVABLE"})
            continue
        old = dest.read_bytes() if dest.is_file() else None
        if write:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if old is not None and digest(old) != expected:
                forensic = dest.parent / "corrupted_originals" / (digest(old) + ".json")
                forensic.parent.mkdir(parents=True, exist_ok=True)
                if forensic.is_file():
                    if forensic.read_bytes() != old:
                        raise ValueError("FORENSIC_ORIGINAL_CONFLICT")
                else:
                    with forensic.open("xb") as handle:
                        handle.write(old)
            dest.write_bytes(found)
            if digest(dest.read_bytes()) != expected:
                raise ValueError("POST_RESTORE_HASH_MISMATCH")
        restored.append({"path": key, "source_path": origin.relative_to(root).as_posix(),
                         "sha256": expected, "action": "RESTORED_EXACT_SHA" if write
                         else "EXACT_SHA_AVAILABLE_NOT_WRITTEN"})
    return {"schema": "MATRIX_OVER25_MISSING_SOURCE_RESTORE_V1",
            "source_refs_checked": len(required), "already_verified": valid,
            "exact_sha_restored_count": len(restored), "exact_sha_restored": restored,
            "unrecoverable_source_count": len(blocked), "unrecoverable": blocked,
            "invalid_forecasts": failed, "modified_frozen_forecasts": False,
            "modified_governed_model": False, "production_p_matrix_authorized": False,
            "telegram_signal_authorized": False, "automatic_wagering": False,
            "real_money": "BLOCKED"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--restore", action="store_true")
    args = parser.parse_args()
    report = recover(args.root, write=args.restore)
    target = args.root / REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True,
                                 indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("source_refs_checked",
          "already_verified", "exact_sha_restored_count",
          "unrecoverable_source_count", "telegram_signal_authorized")},
          sort_keys=True))

if __name__ == "__main__":
    main()
