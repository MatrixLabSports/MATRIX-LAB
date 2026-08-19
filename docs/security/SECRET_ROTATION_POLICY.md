# V14 Secret Rotation Contract

V14 stores secret **metadata only**: logical name, provider reference, version, creation time, expiry time and enabled state. Secret material is intentionally absent.

Rotation evidence records previous/new versions, time, verified actor, revocation of the old version and validation of the new version. Missing, expired, over-age, unverified or unreconciled secrets fail closed. Expiry warnings produce WATCH rather than automatic credential changes.

Actual vault/KMS rotation is outside the isolated V14 environment and remains a future integration requirement.
