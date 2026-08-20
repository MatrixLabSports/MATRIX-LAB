from pathlib import Path


def test_network_permit_binds_exact_resolved_ips():
    source = Path("app/core/provider_network_execution_authorization.py").read_text(encoding="utf-8-sig")
    assert "resolved_ips: tuple[str, ...]" in source
    assert '"resolved_ips": list(dns.resolved_ips)' in source
    assert "resolved_ips=tuple(dns.resolved_ips)" in source
