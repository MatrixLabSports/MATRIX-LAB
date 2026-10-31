from tools.matrix_commercial_architecture_guard import validate

def test_commercial_architecture_policy_is_internally_consistent():
    assert validate()==[]


def test_force_volume_is_rejected_when_canonical_protection_is_disabled(monkeypatch):
    from tools import matrix_commercial_architecture_guard as guard
    original=guard.load

    def load(name):
        data=original(name)
        if name=="MATRIX_COMMERCIAL_PRODUCT_POLICY.json":
            data["sports_governance"]["no_pick_created_to_fill_commercial_quota"]=False
        return data

    monkeypatch.setattr(guard,"load",load)
    assert "FORCE_VOLUME" in guard.validate()


def test_legacy_explicit_force_volume_is_rejected(monkeypatch):
    from tools import matrix_commercial_architecture_guard as guard
    original=guard.load

    def load(name):
        data=original(name)
        if name=="MATRIX_COMMERCIAL_PRODUCT_POLICY.json":
            data["sports_governance"]["force_volume"]=True
        return data

    monkeypatch.setattr(guard,"load",load)
    assert "FORCE_VOLUME" in guard.validate()
