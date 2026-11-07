"""Static regression guard: do not advertise unverified external capabilities."""
from pathlib import Path


def test_recovery_capabilities_are_not_unconditionally_certified():
    source = (Path(__file__).resolve().parents[1] / "tools" / "matrix_quote_recovery_actuator.py").read_text(encoding="utf-8")
    assert '"api_football_automatic":False' in source
    assert '"opera_connector_physical_read_available":None' in source
    assert '"opera_connector_physical_read_verified_this_run":False' in source
    assert '"api_football_automatic":True' not in source
    assert '"opera_connector_physical_read_available":True' not in source
