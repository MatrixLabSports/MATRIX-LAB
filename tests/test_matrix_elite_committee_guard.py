from tools.matrix_elite_committee_guard import load, validate

def test_elite_committee_registry_passes():
    out=validate(load())
    assert out["status"]=="PASS"
    assert out["role_count"]==37

def test_realtime_reliability_role_is_canonical_owner():
    data=load()
    assert data["escalation"]["pipeline_signal_loss_owner"]=="PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER"
    role=next(r for r in data["roles"] if r["id"]=="PRINCIPAL_REALTIME_RELIABILITY_ODDS_ENGINEER")
    assert "provider_failover" in role["owner_of"]
    assert "pre_kickoff_sla" in role["owner_of"]


def test_browser_automation_role_is_canonical_owner():
    data=load()
    assert data["escalation"]["browser_automation_owner"]=="BROWSER_AUTOMATION_SELF_HOSTED_RUNNER_ENGINEER"
    role=next(r for r in data["roles"] if r["id"]=="BROWSER_AUTOMATION_SELF_HOSTED_RUNNER_ENGINEER")
    assert "self_hosted_runner_architecture" in role["owner_of"]
    assert "playwright_browser_automation" in role["owner_of"]
