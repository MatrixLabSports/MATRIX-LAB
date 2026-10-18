from tools.api_football_extended_market_history_warmup import (
    _existing_ids,
    _protected_ids_and_cutoff,
    _prospective_ids,
    _raw_final_candidates,
    _utc,
    select_candidates,
)


def test_raw_final_candidates_are_only_statsrich_source_leagues():
    rows=_raw_final_candidates()
    assert len(rows)==368
    assert {r["league_id"] for r in rows}=={"72","252"}
    assert rows==sorted(rows,key=lambda r:(_utc(r["kickoff_utc"]),int(r["fixture_id"])))


def test_warmup_selection_excludes_all_protected_domains():
    selected,audit=select_candidates(120)
    existing=_existing_ids()
    protected,cutoff=_protected_ids_and_cutoff()
    prospective=_prospective_ids()
    ids={r["fixture_id"] for r in selected}
    assert not (ids & existing)
    assert not (ids & protected)
    assert not (ids & prospective)
    assert all(_utc(r["kickoff_utc"]) < cutoff for r in selected)
    assert audit["protected_final_holdout_count"]==357
    assert audit["raw_final_count"]==368
