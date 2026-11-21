from __future__ import annotations

import json
import os
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Mapping

from tools.cor0203_api_tennis_discovery import (
    ApiTennisDiscoveryClient,
    CHALLENGER_MEN_SINGLES_NAME,
)


TARGET_LAST_NAMES = {"andrade", "shelbayh"}


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def _rows(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list):
        return []
    return [row for row in result if isinstance(row, Mapping)]


def _safe_stats(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    stats = row.get("statistics")
    if not isinstance(stats, list):
        return []
    out = []
    for item in stats:
        if not isinstance(item, Mapping):
            continue
        out.append({
            "player_key": item.get("player_key"),
            "stat_period": item.get("stat_period"),
            "stat_type": item.get("stat_type"),
            "stat_name": item.get("stat_name"),
            "stat_value": item.get("stat_value"),
            "stat_won": item.get("stat_won"),
            "stat_total": item.get("stat_total"),
        })
    return out


def summarize_payload(payload: Mapping[str, Any], *, label: str) -> dict[str, Any]:
    rows = [
        row for row in _rows(payload)
        if str(row.get("event_type_type") or "").strip() == CHALLENGER_MEN_SINGLES_NAME
    ]
    targets = []
    for row in rows:
        names = [
            str(row.get("event_first_player") or ""),
            str(row.get("event_second_player") or ""),
        ]
        joined = " ".join(_norm(x) for x in names)
        if any(last in joined for last in TARGET_LAST_NAMES):
            targets.append({
                "event_key": row.get("event_key"),
                "event_date": row.get("event_date"),
                "event_first_player": names[0],
                "first_player_key": row.get("first_player_key"),
                "event_second_player": names[1],
                "second_player_key": row.get("second_player_key"),
                "event_winner": row.get("event_winner"),
                "event_status": row.get("event_status"),
                "tournament_name": row.get("tournament_name"),
                "tournament_key": row.get("tournament_key"),
                "tournament_round": row.get("tournament_round"),
                "statistics_count": len(_safe_stats(row)),
            })

    sample = next((row for row in rows if _safe_stats(row)), None)
    sample_summary = None
    if sample is not None:
        surface_fields = {
            str(k): v
            for k, v in sample.items()
            if "surface" in str(k).casefold() or "court" in str(k).casefold()
        }
        sample_summary = {
            "event_key": sample.get("event_key"),
            "event_date": sample.get("event_date"),
            "event_first_player": sample.get("event_first_player"),
            "first_player_key": sample.get("first_player_key"),
            "event_second_player": sample.get("event_second_player"),
            "second_player_key": sample.get("second_player_key"),
            "event_winner": sample.get("event_winner"),
            "event_status": sample.get("event_status"),
            "event_final_result": sample.get("event_final_result"),
            "tournament_name": sample.get("tournament_name"),
            "tournament_key": sample.get("tournament_key"),
            "tournament_round": sample.get("tournament_round"),
            "surface_fields": surface_fields,
            "statistics": _safe_stats(sample)[:80],
        }

    return {
        "label": label,
        "challenger_rows": len(rows),
        "rows_with_statistics": sum(1 for row in rows if _safe_stats(row)),
        "target_rows": targets,
        "sample_with_statistics": sample_summary,
    }


def main() -> None:
    key = os.environ.get("API_TENNIS_KEY", "").strip()
    if not key:
        raise SystemExit("API_TENNIS_KEY_REQUIRED")
    client = ApiTennisDiscoveryClient(key)
    historical = client.fixtures(date(2026, 9, 14), date(2026, 9, 14))
    current = client.fixtures(date(2026, 10, 3), date(2026, 10, 3))
    report = {
        "schema": "MATRIX_COR0203_API_TENNIS_STATS_RICH_PROBE_V1",
        "historical_pre_cut": summarize_payload(historical, label="2026-09-14"),
        "current_target_day": summarize_payload(current, label="2026-10-03"),
        "provider_network_calls": client.request_count,
        "post_cut_competitive_data_used_for_model": False,
        "outcomes_used_for_metrics": False,
        "metrics_opened": False,
        "automatic_wagering": False,
        "real_money": "BLOCKED",
    }
    out = Path("evidence/cor0203/api_tennis_stats_rich/MATRIX_COR0203_API_TENNIS_STATS_RICH_PROBE_LAST.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "historical_challenger_rows": report["historical_pre_cut"]["challenger_rows"],
        "historical_rows_with_statistics": report["historical_pre_cut"]["rows_with_statistics"],
        "current_target_rows": len(report["current_target_day"]["target_rows"]),
        "provider_network_calls": report["provider_network_calls"],
        "real_money": report["real_money"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
