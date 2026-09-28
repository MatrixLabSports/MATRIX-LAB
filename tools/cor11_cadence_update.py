from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

BOGOTA = ZoneInfo("America/Bogota")
TARGET_DAYS = 14
DEFAULT_DIR = Path("evidence/cor11")


@dataclass(frozen=True)
class CommitEvidence:
    commit: str
    committer_utc: str
    local_date: str
    message: str
    changed_paths: tuple[str, ...]


def _parse_aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _load_latest(root: Path = DEFAULT_DIR) -> dict[str, Any]:
    last = root / "MATRIX_COR11_CADENCE_LEDGER_LAST.json"
    if last.is_file():
        return json.loads(last.read_text(encoding="utf-8"))
    candidates = sorted(root.glob("MATRIX_COR11_CADENCE_LEDGER_R*.json"))
    if not candidates:
        raise FileNotFoundError("COR11_CADENCE_LEDGER_NOT_FOUND")
    return json.loads(candidates[-1].read_text(encoding="utf-8"))


def _qualifying_path(path: str) -> bool:
    return path.startswith(("evidence/", "app/", "tools/", "tests/", ".github/workflows/"))


def _excluded_message(message: str) -> bool:
    normalized = message.strip().casefold()
    return normalized.startswith("audit(cor11):") or "cor11 cadence" in normalized


def _git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def find_commit_evidence(target: date) -> CommitEvidence | None:
    start_local = datetime.combine(target, time.min, tzinfo=BOGOTA)
    stop_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(timezone.utc).isoformat()
    stop_utc = stop_local.astimezone(timezone.utc).isoformat()
    raw = _git(
        "log",
        "--format=%H%x09%cI%x09%s",
        f"--since={start_utc}",
        f"--before={stop_utc}",
        "HEAD",
    )
    if not raw:
        return None
    for line in raw.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        commit, stamp, message = parts
        if _excluded_message(message):
            continue
        changed = tuple(
            p for p in _git("show", "--pretty=", "--name-only", commit).splitlines()
            if p.strip()
        )
        if not any(_qualifying_path(path) for path in changed):
            continue
        local = _parse_aware(stamp).astimezone(BOGOTA).date()
        if local != target:
            continue
        return CommitEvidence(
            commit=commit,
            committer_utc=_parse_aware(stamp).isoformat(),
            local_date=target.isoformat(),
            message=message,
            changed_paths=changed,
        )
    return None


def advance(
    ledger: Mapping[str, Any],
    *,
    target: date,
    evidence: CommitEvidence,
) -> dict[str, Any]:
    dates = [date.fromisoformat(str(x)) for x in ledger.get("dates", [])]
    if not dates:
        raise ValueError("COR11_DATES_MISSING")
    if target in dates:
        return dict(ledger)
    expected = dates[-1] + timedelta(days=1)
    if target != expected:
        raise ValueError(
            f"COR11_NON_CONSECUTIVE_DATE:expected={expected.isoformat()}:got={target.isoformat()}"
        )
    if evidence.local_date != target.isoformat():
        raise ValueError("COR11_EVIDENCE_DATE_MISMATCH")

    output = dict(ledger)
    output["revision"] = f"CALENDAR_{target.strftime('%Y%m%d')}"
    output["correction"] = "COR11"
    output["timezone"] = "America/Bogota"
    output["target_days"] = TARGET_DAYS
    output["dates"] = [d.isoformat() for d in dates] + [target.isoformat()]
    output["real_consecutive_days"] = len(output["dates"])
    output["status"] = "RESOLVED" if len(output["dates"]) >= TARGET_DAYS else "IN_PROGRESS"
    rules = dict(output.get("rules") or {})
    rules.update({
        "utc_rollover_used": False,
        "backfill": False,
        "synthetic_days": False,
        "real_money": "BLOCKED",
    })
    output["rules"] = rules
    physical = dict(output.get("new_physical_evidence") or {})
    physical[target.isoformat()] = {
        "commit": evidence.commit,
        "committer_utc": evidence.committer_utc,
        "local_date": evidence.local_date,
        "message": evidence.message,
        "changed_paths": list(evidence.changed_paths),
    }
    output["new_physical_evidence"] = physical
    return output


def persist(root: Path, payload: Mapping[str, Any], *, target: date) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    snapshot = root / f"MATRIX_COR11_CADENCE_LEDGER_{target.strftime('%Y%m%d')}.json"
    last = root / "MATRIX_COR11_CADENCE_LEDGER_LAST.json"
    text = json.dumps(dict(payload), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    snapshot.write_text(text, encoding="utf-8")
    last.write_text(text, encoding="utf-8")
    if int(payload["real_consecutive_days"]) >= TARGET_DAYS:
        closure = root / "MATRIX_COR11_CLOSURE_EVIDENCE.json"
        closure.write_text(
            json.dumps(
                {
                    "schema": "MATRIX_COR11_CLOSURE_EVIDENCE_V1",
                    "correction": "COR11",
                    "criterion": "cadence documented and respected for >=2 consecutive weeks",
                    "real_consecutive_days": payload["real_consecutive_days"],
                    "dates": payload["dates"],
                    "backfill": False,
                    "synthetic_days": False,
                    "real_money": "BLOCKED",
                    "result": "ACCEPTANCE_EVIDENCE_SATISFIED",
                },
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
    return snapshot, last


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", help="Bogota calendar date YYYY-MM-DD; default=previous completed Bogota day")
    parser.add_argument("--root", default=str(DEFAULT_DIR))
    args = parser.parse_args()

    root = Path(args.root)
    now_local = datetime.now(timezone.utc).astimezone(BOGOTA)
    target = (
        date.fromisoformat(args.target_date)
        if args.target_date
        else now_local.date() - timedelta(days=1)
    )
    ledger = _load_latest(root)
    if target.isoformat() in set(str(x) for x in ledger.get("dates", [])):
        print(json.dumps({
            "status": "ALREADY_RECORDED",
            "target_date": target.isoformat(),
            "real_consecutive_days": ledger.get("real_consecutive_days"),
            "target_days": ledger.get("target_days", TARGET_DAYS),
        }, sort_keys=True))
        return

    evidence = find_commit_evidence(target)
    if evidence is None:
        raise SystemExit(f"COR11_NO_QUALIFYING_REAL_EVIDENCE:{target.isoformat()}")

    updated = advance(ledger, target=target, evidence=evidence)
    snapshot, last = persist(root, updated, target=target)
    print(json.dumps({
        "status": updated["status"],
        "target_date": target.isoformat(),
        "real_consecutive_days": updated["real_consecutive_days"],
        "target_days": updated["target_days"],
        "evidence_commit": evidence.commit,
        "snapshot": str(snapshot),
        "last": str(last),
        "real_money": updated["rules"]["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
