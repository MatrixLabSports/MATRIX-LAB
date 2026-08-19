# MATRIX V14 — Trusted Attestation + Secret Rotation + SCA Contract

Estado: **VERIFIED_IN_ISOLATED_ENVIRONMENT / NOT_INTEGRATED / NOT_PRODUCTION_CERTIFIED**.

V14 adds an Ed25519 attestation contract, trusted-key validity/revocation/purpose controls, metadata-only secret rotation governance, a strict SCA evidence contract tied to source commit + dependency lock, and a fail-closed trusted supply-chain gate.

Important: isolated test keys are not production trust anchors. No private key or secret material is stored in this package. A PASS in this isolated V14 gate means only that the contract behaves correctly with test evidence; it does not certify the user's Windows repository or authorize a production release.
