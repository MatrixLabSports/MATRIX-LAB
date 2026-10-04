from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: Any) -> str:
    return hashlib.sha256(_canon(value).encode("utf-8")).hexdigest()


def _norm(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _stable_identity(row: Mapping[str, Any]) -> str:
    p1 = row.get("player1") if isinstance(row.get("player1"), Mapping) else {}
    p2 = row.get("player2") if isinstance(row.get("player2"), Mapping) else {}
    ids = sorted(str(x).strip() for x in (p1.get("id"), p2.get("id")) if str(x or "").strip())
    names = sorted(_norm(x) for x in (p1.get("name"), p2.get("name")) if _norm(x))
    players = {"ids": ids} if len(ids) == 2 else {"names": names}
    key = {
        "provider_channel": _norm(row.get("provider_channel")),
        "circuit_detail": _norm(row.get("circuit_detail")),
        "tournament": str(row.get("tournament_id") or _norm(row.get("tournament_name"))),
        "round": _norm(row.get("round")),
        "event_format": _norm(row.get("event_format")),
        "players": players,
    }
    return _sha(key)


def _load(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("WORLD_INVENTORY_ROOT_NOT_OBJECT")
    return value


def accumulate(current: Mapping[str, Any], prior: Mapping[str, Any] | None) -> dict[str, Any]:
    target = str(current.get("target_date_bogota") or "")
    if not target:
        raise ValueError("CURRENT_TARGET_DATE_MISSING")
    if prior is not None and str(prior.get("target_date_bogota") or "") != target:
        raise ValueError("WORLD_INVENTORY_TARGET_DATE_MISMATCH")

    prior_events = list(prior.get("events") or []) if prior else []
    current_events = list(current.get("events") or [])
    if not all(isinstance(x, Mapping) for x in prior_events + current_events):
        raise ValueError("WORLD_INVENTORY_EVENTS_NOT_OBJECTS")

    merged: dict[str, dict[str, Any]] = {}
    retained_prior_keys: set[str] = set()
    for source, rows in (("prior", prior_events), ("current", current_events)):
        for raw in rows:
            row = dict(raw)
            stable = _stable_identity(row)
            row["stable_physical_identity_key"] = stable
            old = merged.get(stable)
            if old is None:
                merged[stable] = row
                if source == "prior":
                    retained_prior_keys.add(stable)
                continue
            aliases = set(old.get("source_event_aliases") or [])
            for value in (old.get("source_event_id"), row.get("source_event_id")):
                if value:
                    aliases.add(str(value))
            if source == "current":
                row["source_event_aliases"] = sorted(aliases)
                merged[stable] = row
                retained_prior_keys.discard(stable)
            else:
                old["source_event_aliases"] = sorted(aliases)

    events = list(merged.values())
    events.sort(key=lambda row: (
        str(row.get("event_start_utc") or ""),
        str(row.get("provider_channel") or ""),
        str(row.get("tournament_id") or ""),
        str(row.get("match_id") or ""),
        str(row.get("stable_physical_identity_key") or ""),
    ))

    current_keys = {_stable_identity(row) for row in current_events}
    prior_keys = {_stable_identity(row) for row in prior_events}
    newly_discovered = current_keys - prior_keys
    prior_only = prior_keys - current_keys

    by_family = Counter(str(row.get("circuit_family") or "UNKNOWN") for row in events)
    by_detail = Counter(str(row.get("circuit_detail") or "UNKNOWN") for row in events)
    by_format = Counter(str(row.get("event_format") or "UNKNOWN") for row in events)
    candidates = [
        row.get("source_event_id")
        for row in events
        if isinstance(row.get("model_derivation"), Mapping)
        and row["model_derivation"].get("domain_candidate") is True
        and row.get("source_event_id")
    ]

    out = dict(current)
    out["events"] = events
    out["world_calendar_inventory_count"] = len(events)
    out["events_by_family"] = {
        "ATP": by_family.get("ATP", 0),
        "WTA": by_family.get("WTA", 0),
        "ITF": by_family.get("ITF", 0),
    }
    out["events_by_detail"] = dict(sorted(by_detail.items()))
    out["events_by_format"] = dict(sorted(by_format.items()))
    lanes = dict(out.get("derived_lanes") or {})
    cor = dict(lanes.get("COR02_COR03_ATP_CHALLENGER_HARD") or {})
    cor.update({
        "domain_candidate_count": len(candidates),
        "source_event_ids": candidates,
        "feeds_model_automatically": False,
        "governed_pipeline_remains_authoritative": True,
    })
    lanes["COR02_COR03_ATP_CHALLENGER_HARD"] = cor
    wta = dict(lanes.get("WTA") or {})
    wta.update({"inventory_count": by_family.get("WTA", 0), "current_governed_model": None, "feeds_COR02_COR03": False})
    lanes["WTA"] = wta
    itf = dict(lanes.get("ITF") or {})
    itf.update({"inventory_count": by_family.get("ITF", 0), "current_governed_model": None, "feeds_COR02_COR03": False})
    lanes["ITF"] = itf
    out["derived_lanes"] = lanes
    out["accumulation"] = {
        "policy": "MONOTONIC_UNION_BY_STABLE_PHYSICAL_IDENTITY",
        "prior_count": len(prior_events),
        "current_fetch_count": len(current_events),
        "cumulative_count": len(events),
        "newly_discovered_count": len(newly_discovered),
        "retained_prior_only_count": len(prior_only),
        "never_decrease_within_day": True,
    }
    out["p_matrix"] = "NOT_GENERATED"
    out["metrics_opened"] = False
    out["automatic_wagering"] = False
    out["real_money"] = "BLOCKED"
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", required=True)
    parser.add_argument("--existing")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    current = _load(Path(args.current))
    assert current is not None
    prior = _load(Path(args.existing)) if args.existing else None
    report = accumulate(current, prior)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": report.get("status"),
        "target_date_bogota": report.get("target_date_bogota"),
        "current_fetch_count": report["accumulation"]["current_fetch_count"],
        "prior_count": report["accumulation"]["prior_count"],
        "cumulative_count": report["accumulation"]["cumulative_count"],
        "retained_prior_only_count": report["accumulation"]["retained_prior_only_count"],
        "real_money": report.get("real_money"),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
