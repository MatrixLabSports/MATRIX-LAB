from tools.matrix_football_free_provider_catalog import build

def test_documentary_catalog_is_fail_closed():
    result=build()
    assert result["status"]=="DOCUMENTARY_CATALOG_ONLY_FAIL_CLOSED"
    assert result["source_order"]==["SOFASCORE","FLASHSCORE","APIS"]
    assert result["network_calls_performed"]==0
    assert result["signal_generation_authorized"] is False
    assert result["real_money"]=="BLOCKED"
    assert result["automatic_wagering"] is False

def test_catalog_has_unique_provider_ids_and_source_urls():
    providers=build()["providers"]
    assert len(providers)>=6
    assert len({p["id"] for p in providers})==len(providers)
    assert all(p["official"].startswith("https://") for p in providers)
