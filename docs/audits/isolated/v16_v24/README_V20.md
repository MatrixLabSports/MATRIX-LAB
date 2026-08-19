# MATRIX-LAB-SPORTS V20

V20 adds provider operational fitness, portfolio and failover governance on top of V19 provider-rights controls.

Modules:
- `matrix_security/provider_operational.py`
- `matrix_security/provider_portfolio.py`
- `matrix_security/provider_failover.py`
- `matrix_security/provider_portfolio_gate.py`

Important implementation decision: operational percentages are integer basis points (`10000 == 100%`) and costs are integer cents. This preserves deterministic canonical fingerprints and avoids float-dependent release evidence.

The package is an isolated development artifact. It is not installed in the user's Windows repository until a later consolidated, fail-closed installer is explicitly run and verified there.
