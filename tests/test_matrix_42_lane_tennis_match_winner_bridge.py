from datetime import datetime, timezone
from pathlib import Path
import json

from tools.matrix_42_lane_tennis_match_winner_bridge import build_rows


def test_only_future_prematch_rows_are_admitted(tmp_path:Path):
    hard=tmp_path/"hard"; hard.mkdir()
    data={
      "historical_backfill":"FORBIDDEN","outcomes_read":0,"real_money":"BLOCKED","batch_sha256":"a"*64,
      "observations":[{
        "event_id":"e1","physical_event_key":"p1","event_start_utc":"2026-10-26T03:00:00+00:00","freeze_at_utc":"2026-10-24T19:00:00+00:00",
        "feature_snapshot_sha256":"b"*64,"alphabetical_player_a":"A","alphabetical_player_b":"B",
        "elo":{"p_player_a":0.6,"model_id":"ELO"},"glicko":{"p_player_a":0.58,"model_id":"GLICKO"},
        "outcome":None,"metrics_opened":False
      },{
        "event_id":"old","physical_event_key":"old","event_start_utc":"2026-10-24T19:00:00+00:00","freeze_at_utc":"2026-10-24T18:00:00+00:00",
        "feature_snapshot_sha256":"c"*64,"alphabetical_player_a":"C","alphabetical_player_b":"D",
        "elo":{"p_player_a":0.5,"model_id":"ELO"},"glicko":{"p_player_a":0.5,"model_id":"GLICKO"},
        "outcome":None,"metrics_opened":False
      }]
    }
    (hard/"MATRIX_COR0203_HOLDOUT_BATCH_T.json").write_text(json.dumps(data),encoding="utf-8")
    clay=tmp_path/"clay.jsonl"; clay.write_text("",encoding="utf-8")
    rows,audit=build_rows(hard_dir=hard,clay_obs=clay,now_utc=datetime(2026,10,24,20,0,tzinfo=timezone.utc),existing_keys=set())
    assert len(rows)==1
    assert rows[0]["market_lane"]=="MATCH_WINNER"
    assert rows[0]["event_id"]=="e1"
    assert rows[0]["counts_toward_100_300_600"] is True
    assert audit["protections"]["historical_backfill_forbidden"] is True
