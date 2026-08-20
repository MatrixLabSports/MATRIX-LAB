import pytest

from app.application.football.governed_acquisition_queue import build_football_acquisition_queue
from app.application.tennis.governed_acquisition_queue import build_tennis_acquisition_queue
from app.core.governed_acquisition_queue import AcquisitionCandidate, ProviderBudget

def c(
    sport,
    subject,
    *,
    provider="P1",
    score=10.0,
    rows=5,
    cost=1,
    rights="PASS",
    identity="PASS",
    chronology="PASS",
    provider_status="PASS",
    disposition="PRIORITIZE",
):
    return AcquisitionCandidate(
        sport=sport,
        subject_key=subject,
        provider_key=provider,
        competition_key="C1",
        season_key="2026",
        disposition=disposition,
        priority_score=score,
        expected_rows=rows,
        estimated_request_cost=cost,
        rights_status=rights,
        identity_status=identity,
        chronology_status=chronology,
        provider_status=provider_status,
        source_fingerprint="a" * 64,
    )

def budget(requests=10, rows=100):
    return [ProviderBudget("P1", max_requests=requests, max_rows=rows)]

def test_efficiency_ranking():
    q = build_tennis_acquisition_queue(
        candidates=[
            c("tennis", "A", score=20, cost=4),
            c("tennis", "B", score=15, cost=1),
        ],
        budgets=budget(),
    )
    assert [row["subject_key"] for row in q["queue"]] == ["B", "A"]

def test_request_budget_blocks():
    q = build_football_acquisition_queue(
        candidates=[
            c("football", "A", score=20, cost=2),
            c("football", "B", score=10, cost=2),
        ],
        budgets=budget(requests=2),
    )
    assert len(q["queue"]) == 1
    assert any("PROVIDER_REQUEST_BUDGET_EXCEEDED" in x["blockers"] for x in q["quarantined"])

def test_row_budget_blocks():
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", "A", rows=8)],
        budgets=budget(rows=5),
    )
    assert q["queue"] == []
    assert "PROVIDER_ROW_BUDGET_EXCEEDED" in q["quarantined"][0]["blockers"]

@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("rights", "WATCH", "RIGHTS_NOT_VERIFIED"),
        ("identity", "WATCH", "IDENTITY_NOT_VERIFIED"),
        ("chronology", "BLOCK", "CHRONOLOGY_NOT_VERIFIED"),
        ("provider_status", "WATCH", "PROVIDER_NOT_READY"),
    ],
)
def test_governance_overrides_score(field, value, reason):
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", "Q", score=9999, **{field: value})],
        budgets=budget(100, 1000),
    )
    assert q["queue"] == []
    assert reason in q["quarantined"][0]["blockers"]

def test_research_only_allowed():
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", "R", rights="RESEARCH_ONLY")],
        budgets=budget(),
    )
    assert len(q["queue"]) == 1
    assert q["queue"][0]["rights_status"] == "RESEARCH_ONLY"

def test_cross_sport_blocks():
    with pytest.raises(ValueError, match="CROSS_SPORT_CANDIDATE_CONTAMINATION"):
        build_football_acquisition_queue(
            candidates=[c("football", "F"), c("tennis", "T")],
            budgets=budget(),
        )

def test_missing_budget_quarantines():
    q = build_football_acquisition_queue(
        candidates=[c("football", "F", provider="PX")],
        budgets=budget(),
    )
    assert q["queue"] == []
    assert "MISSING_PROVIDER_BUDGET" in q["quarantined"][0]["blockers"]

def test_queue_limit_respected():
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", str(i), score=100-i) for i in range(5)],
        budgets=budget(100, 1000),
        queue_limit=2,
    )
    assert len(q["queue"]) == 2

def test_queue_fingerprint_changes():
    q1 = build_football_acquisition_queue(
        candidates=[c("football", "F", score=10)],
        budgets=budget(),
    )
    q2 = build_football_acquisition_queue(
        candidates=[c("football", "F", score=11)],
        budgets=budget(),
    )
    assert q1["queue_fingerprint"] != q2["queue_fingerprint"]

def test_zero_request_cost_blocks():
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", "Z", cost=0, rows=5)],
        budgets=budget(),
    )
    assert q["queue"] == []
    assert "INVALID_ZERO_REQUEST_COST" in q["quarantined"][0]["blockers"]

def test_duplicate_budget_blocks():
    with pytest.raises(ValueError, match="DUPLICATE_PROVIDER_BUDGET"):
        build_football_acquisition_queue(
            candidates=[],
            budgets=[
                ProviderBudget("P1", 10, 100),
                ProviderBudget("P1", 20, 200),
            ],
        )

def test_safety_flags_false():
    q = build_tennis_acquisition_queue(
        candidates=[c("tennis", "SAFE")],
        budgets=budget(),
    )
    assert q["automatic_model_promotion"] is False
    assert q["automatic_provider_switch"] is False
    assert q["automatic_wagering"] is False
