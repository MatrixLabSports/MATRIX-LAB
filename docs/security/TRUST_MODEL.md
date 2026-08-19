# V14 Trust Model

- Production trust must be anchored outside the release being verified.
- V14 uses Ed25519 signatures and key-purpose restrictions for the attestation contract.
- A release-attestation key and an SCA-attestation key may be separated by policy.
- Key validity windows and revocation are checked fail-closed.
- Test keys created in the isolated environment are explicitly **not production trust anchors**.
- No private signing key is persisted in the V14 evidence bundle.
- A cryptographically valid signature does not prove the underlying claim is true unless the issuer/key is independently trusted and the predicate is itself evidence-backed.
