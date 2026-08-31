from datetime import datetime, timedelta, timezone
import pytest

from matrix_elite.data_admission import admit_training_snapshot
from matrix_elite.identity import CanonicalIdentityRegistry, IdentityBinding, IdentityGovernanceEvent
from matrix_elite.pit import (
    PITRecord,
    audit_minimum_coverage,
    audit_revision_graph,
    snapshot_as_of,
    snapshot_manifest,
)
from matrix_elite.rights import RightsProfile, RightsRegistry

UTC = timezone.utc
T0 = datetime(2024, 1, 1, tzinfo=UTC)


def rec(*, key="k", provider="p", rev=1, available=None, supersedes=None, year=2024, market="1X2"):
    available = available or T0
    return PITRecord(
        record_key=key,
        provider=provider,
        sport="football",
        competition="league",
        market=market,
        observed_at=available - timedelta(seconds=1),
        available_at=available,
        event_start_at=datetime(year, 6, 1, tzinfo=UTC),
        revision_id=f"{provider}:{key}:r{rev}",
        revision_number=rev,
        payload_sha256=(hex(rev)[2:] * 64)[:64],
        supersedes_revision_id=supersedes,
    )


def evt(action, *, ids=("c1",), keys=(("p", "1"),)):
    return IdentityGovernanceEvent(
        event_id=f"e-{action}",
        action=action,
        canonical_entity_ids=tuple(ids),
        provider_keys=tuple(keys),
        approved_by="independent-auditor",
        approved_at=T0,
        evidence_sha256="f" * 64,
        reason="adversarial identity correction",
    )


def rights(provider="p", *, training=True, expires=None, terminated=None):
    return RightsProfile(
        provider=provider,
        research=True,
        retention=True,
        derivatives=True,
        model_training=training,
        display=False,
        redistribution=False,
        commercial_use=False,
        expires_at=expires,
        evidence_sha256="e" * 64,
        effective_from=T0 - timedelta(days=1),
        terminated_at=terminated,
        termination_reason="terminated" if terminated else None,
    )


def test_pit_snapshot_never_uses_late_revision_in_historical_cutoff():
    r1 = rec(rev=1, available=T0)
    r2 = rec(rev=2, available=T0 + timedelta(days=10), supersedes=r1.revision_id)
    assert snapshot_as_of([r1, r2], as_of=T0 + timedelta(days=1)) == (r1,)
    assert snapshot_as_of([r1, r2], as_of=T0 + timedelta(days=11)) == (r2,)


def test_pit_revision_graph_rejects_missing_parent_and_cross_key_supersession():
    missing = rec(rev=2, supersedes="absent")
    assert "SUPERSEDED_REVISION_NOT_FOUND" in {x.code for x in audit_revision_graph([missing])}
    parent = rec(key="a", rev=1)
    child = rec(key="b", rev=2, available=T0 + timedelta(days=1), supersedes=parent.revision_id)
    assert "CROSS_KEY_SUPERSESSION" in {x.code for x in audit_revision_graph([parent, child])}


def test_pit_manifest_is_deterministic_and_cutoff_sensitive():
    r1 = rec(rev=1, available=T0)
    r2 = rec(rev=2, available=T0 + timedelta(days=10), supersedes=r1.revision_id)
    a = snapshot_manifest([r2, r1], as_of=T0 + timedelta(days=1))
    b = snapshot_manifest([r1, r2], as_of=T0 + timedelta(days=1))
    c = snapshot_manifest([r1, r2], as_of=T0 + timedelta(days=11))
    assert a.snapshot_sha256 == b.snapshot_sha256
    assert a.snapshot_sha256 != c.snapshot_sha256


def test_coverage_cube_is_market_competition_year_specific():
    rows = [rec(key=f"k{i}", year=2023) for i in range(3)] + [rec(key="z", year=2024)]
    req = {
        ("football", "league", "1X2", 2023): 3,
        ("football", "league", "1X2", 2024): 2,
    }
    result = audit_minimum_coverage(rows, requirements=req)
    assert result[("football", "league", "1X2", 2023)]["pass"] is True
    assert result[("football", "league", "1X2", 2024)]["pass"] is False


def test_identity_conflict_quarantines_provider_key_fail_closed():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p", "1", "c1", .99, "a" * 64, entity_type="PLAYER"))
    with pytest.raises(ValueError, match="REBIND"):
        r.bind(IdentityBinding("p", "1", "c2", .99, "b" * 64, entity_type="PLAYER"))
    with pytest.raises(ValueError, match="QUARANTINED"):
        r.resolve("p", "1")


def test_identity_merge_requires_governance_and_updates_crosswalk():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p1", "1", "c1", .99, "a" * 64, entity_type="PLAYER"))
    r.bind(IdentityBinding("p2", "2", "c2", .99, "b" * 64, entity_type="PLAYER"))
    r.merge(source_ids=("c1", "c2"), target_id="c3", event=evt("MERGE", ids=("c1", "c2", "c3"), keys=(("p1", "1"), ("p2", "2"))))
    assert r.resolve("p1", "1") == "c3"
    assert r.resolve("p2", "2") == "c3"
    assert r.governance_event_count == 1


def test_identity_split_requires_exact_assignment_of_all_source_bindings():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p1", "1", "c1", .99, "a" * 64, entity_type="PLAYER"))
    r.bind(IdentityBinding("p2", "2", "c1", .99, "b" * 64, entity_type="PLAYER"))
    with pytest.raises(ValueError, match="COVER_SOURCE_EXACTLY"):
        r.split(source_id="c1", assignments={("p1", "1"): "x"}, event=evt("SPLIT", ids=("c1", "x", "y"), keys=(("p1", "1"), ("p2", "2"))))
    r.split(source_id="c1", assignments={("p1", "1"): "x", ("p2", "2"): "y"}, event=evt("SPLIT", ids=("c1", "x", "y"), keys=(("p1", "1"), ("p2", "2"))))
    assert r.resolve("p1", "1") == "x" and r.resolve("p2", "2") == "y"


def test_identity_coverage_exposes_missing_and_quarantine():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p", "1", "c1", .99, "a" * 64, entity_type="PLAYER"))
    r.bind(IdentityBinding("p", "2", "c2", .80, "b" * 64, status="REVIEW_REQUIRED", entity_type="PLAYER"))
    cov = r.crosswalk_coverage({("p", "1"), ("p", "2"), ("p", "3")})
    assert cov == {"total": 3, "resolved": 1, "quarantined_or_review": 1, "missing": 1, "resolved_rate": 1 / 3}


def test_rights_expiry_and_termination_block_use():
    rr = RightsRegistry()
    expired = rights(expires=T0 + timedelta(days=1))
    rr.register(expired)
    assert rr.audit_use(providers=["p"], purposes=["model_training"], at=T0)["pass"] is True
    assert rr.audit_use(providers=["p"], purposes=["model_training"], at=T0 + timedelta(days=2))["pass"] is False


def test_rights_missing_profile_and_forbidden_training_fail_closed():
    rr = RightsRegistry()
    rr.register(rights(training=False))
    out = rr.audit_use(providers=["p", "unknown"], purposes=["model_training"], at=T0)
    codes = {x["code"] for x in out["failures"]}
    assert "RIGHTS_PURPOSE_FORBIDDEN:model_training" in codes
    assert "RIGHTS_PROFILE_NOT_FOUND" in codes


def test_training_admission_requires_pit_identity_and_rights_together():
    rows = [rec(key="event-history", provider="p")]
    ids = CanonicalIdentityRegistry()
    ids.bind(IdentityBinding("p", "player-1", "cp1", .99, "a" * 64, entity_type="PLAYER"))
    rr = RightsRegistry(); rr.register(rights())
    ok = admit_training_snapshot(rows, as_of=T0 + timedelta(hours=1), identity_registry=ids, identity_keys=[("p", "player-1")], rights_registry=rr)
    assert ok.admitted and ok.snapshot_sha256 and ok.record_count == 1

    bad = admit_training_snapshot(rows, as_of=T0 + timedelta(hours=1), identity_registry=ids, identity_keys=[("p", "missing")], rights_registry=rr)
    assert not bad.admitted and any("IDENTITY" in x for x in bad.codes)


def test_training_admission_blocks_provider_without_training_rights():
    rows = [rec(key="event-history", provider="p")]
    ids = CanonicalIdentityRegistry(); ids.bind(IdentityBinding("p", "1", "c", .99, "a" * 64, entity_type="PLAYER"))
    rr = RightsRegistry(); rr.register(rights(training=False))
    out = admit_training_snapshot(rows, as_of=T0 + timedelta(hours=1), identity_registry=ids, identity_keys=[("p", "1")], rights_registry=rr)
    assert not out.admitted and any("RIGHTS" in x for x in out.codes)


def test_pit_revision_graph_rejects_forks_gaps_and_cycles():
    root = rec(key="fork", rev=1, available=T0)
    child_a = rec(key="fork", rev=2, available=T0 + timedelta(days=1), supersedes=root.revision_id)
    child_b = PITRecord(
        record_key="fork", provider="p", sport="football", competition="league", market="1X2",
        observed_at=T0 + timedelta(days=2) - timedelta(seconds=1), available_at=T0 + timedelta(days=2),
        event_start_at=datetime(2024, 6, 1, tzinfo=UTC), revision_id="p:fork:r3b", revision_number=3,
        payload_sha256="3"*64, supersedes_revision_id=root.revision_id,
    )
    codes = {x.code for x in audit_revision_graph([root, child_a, child_b])}
    assert "REVISION_FORK" in codes and "REVISION_NUMBER_GAP" in codes

    a = PITRecord("cycle", "p", "football", "league", "1X2", T0, T0, datetime(2024,6,1,tzinfo=UTC), "a", 1, "a"*64, "b")
    b = PITRecord("cycle", "p", "football", "league", "1X2", T0, T0, datetime(2024,6,1,tzinfo=UTC), "b", 2, "b"*64, "a")
    assert "REVISION_CYCLE" in {x.code for x in audit_revision_graph([a,b])}


def test_identity_canonical_entity_type_conflict_is_quarantined():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p1", "player", "c1", .99, "a"*64, entity_type="PLAYER"))
    with pytest.raises(ValueError, match="ENTITY_TYPE_CONFLICT"):
        r.bind(IdentityBinding("p2", "team", "c1", .99, "b"*64, entity_type="TEAM"))


def test_identity_merge_cannot_cross_entity_types():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p1", "1", "player-c", .99, "a"*64, entity_type="PLAYER"))
    r.bind(IdentityBinding("p2", "2", "team-c", .99, "b"*64, entity_type="TEAM"))
    with pytest.raises(ValueError, match="MERGE_ENTITY_TYPE_CONFLICT"):
        r.merge(source_ids=("player-c","team-c"), target_id="bad", event=evt("MERGE", ids=("player-c","team-c","bad"), keys=(("p1","1"),("p2","2"))))


def test_identity_manifest_hash_is_order_independent():
    a = CanonicalIdentityRegistry(); b = CanonicalIdentityRegistry()
    x = IdentityBinding("p1","1","c1",.99,"a"*64,entity_type="PLAYER")
    y = IdentityBinding("p2","2","c2",.99,"b"*64,entity_type="PLAYER")
    a.bind(x); a.bind(y); b.bind(y); b.bind(x)
    assert a.manifest_sha256() == b.manifest_sha256()


def test_rights_profile_update_requires_explicit_version_lineage():
    rr = RightsRegistry()
    old = rights(expires=T0 + timedelta(days=30))
    rr.register(old)
    new = RightsProfile(
        provider="p", research=True, retention=True, derivatives=True, model_training=True,
        display=False, redistribution=False, commercial_use=False, expires_at=T0 + timedelta(days=60),
        evidence_sha256="f"*64, effective_from=T0,
    )
    with pytest.raises(ValueError, match="VERSIONED_GOVERNANCE"):
        rr.register(new)
    rr.register(new, supersedes_evidence_sha256=old.evidence_sha256)
    assert len(rr.history("p")) == 2 and rr.get("p").evidence_sha256 == "f"*64


def test_rights_termination_is_effective_at_termination_timestamp():
    rr = RightsRegistry(); rr.register(rights(terminated=T0 + timedelta(hours=2)))
    assert rr.audit_use(providers=["p"], purposes=["research"], at=T0 + timedelta(hours=1))["pass"]
    assert not rr.audit_use(providers=["p"], purposes=["research"], at=T0 + timedelta(hours=2))["pass"]


def test_identity_merge_is_point_in_time_and_does_not_rewrite_prior_crosswalk():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p1","1","c1",.99,"a"*64,entity_type="PLAYER",available_at=T0))
    r.bind(IdentityBinding("p2","2","c2",.99,"b"*64,entity_type="PLAYER",available_at=T0))
    merge_at = T0 + timedelta(days=10)
    event = IdentityGovernanceEvent("merge-pit","MERGE",("c1","c2","c3"),(("p1","1"),("p2","2")),"auditor",merge_at,"f"*64,"duplicate confirmed")
    r.merge(source_ids=("c1","c2"),target_id="c3",event=event)
    assert r.resolve("p1","1",as_of=T0+timedelta(days=5)) == "c1"
    assert r.resolve("p1","1",as_of=T0+timedelta(days=11)) == "c3"


def test_identity_binding_not_available_yet_is_not_resolved_in_backtest():
    r = CanonicalIdentityRegistry()
    r.bind(IdentityBinding("p","1","c",.99,"a"*64,entity_type="PLAYER",available_at=T0+timedelta(days=2)))
    with pytest.raises(KeyError, match="NOT_FOUND_AS_OF"):
        r.resolve("p","1",as_of=T0+timedelta(days=1))
    assert r.resolve("p","1",as_of=T0+timedelta(days=3)) == "c"


def test_rights_versioning_is_point_in_time():
    rr = RightsRegistry()
    old = RightsProfile("p",True,True,True,True,False,False,False,None,"a"*64,effective_from=T0)
    new = RightsProfile("p",True,True,True,False,False,False,False,None,"b"*64,effective_from=T0+timedelta(days=10))
    rr.register(old)
    rr.register(new,supersedes_evidence_sha256=old.evidence_sha256)
    assert rr.audit_use(providers=["p"],purposes=["model_training"],at=T0+timedelta(days=5))["pass"]
    assert not rr.audit_use(providers=["p"],purposes=["model_training"],at=T0+timedelta(days=11))["pass"]


def test_training_admission_respects_identity_available_at():
    rows=[rec(key="hist",provider="p")]
    ids=CanonicalIdentityRegistry(); ids.bind(IdentityBinding("p","1","c",.99,"a"*64,entity_type="PLAYER",available_at=T0+timedelta(days=2)))
    rr=RightsRegistry(); rr.register(rights())
    out=admit_training_snapshot(rows,as_of=T0+timedelta(days=1),identity_registry=ids,identity_keys=[("p","1")],rights_registry=rr)
    assert not out.admitted and any("IDENTITY_NOT_FOUND_AS_OF" in code for code in out.codes)
