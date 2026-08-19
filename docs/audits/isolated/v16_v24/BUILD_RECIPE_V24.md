# V24 Isolated Build Recipe

1. Start from the verified V23 isolated source tree.
2. Add decision-time replay, accountability attribution, independent learning-integrity review, and accountability ledger modules.
3. Run V24 targeted tests with `python -m pytest tests/test_security_v24_decision_accountability.py -q -p no:cacheprovider`.
4. Run the complete isolated V12–V24 test suite with `python -m pytest tests -q -p no:cacheprovider`.
5. Compile `matrix_security` and `matrix_release`.
6. Import every product module.
7. Run AST boundary audit for football/tennis imports in neutral infrastructure.
8. Run hardcoded-secret scan over product Python source.
9. Generate the V24 source manifest using SHA-256.
10. Build the release ZIP twice with deterministic metadata and require identical SHA-256.

This package is isolated evidence only. It is not installed in the user's Windows repository and does not authorize production, model promotion, provider switching, or wagering.
