# V14 SCA Integration Contract

External SCA evidence must be tied to the exact source commit and exact dependency-lock SHA-256. The evidence records scanner identity/version, database freshness, scan timestamp, result-artifact SHA-256, exit code and normalized findings.

HIGH or CRITICAL findings block. MEDIUM findings require review. Stale/future evidence, unapproved scanners, non-zero exit codes, commit mismatch and lock mismatch block.

V14 defines and tests this contract; it does **not** claim that a fresh external production SCA scan was executed in the user's repository.
