## Incident 1: CrashLoopBackOff on all app pods
- Cause: tracing needed GCP credentials
- Fix: ENABLE_TRACING / ENABLE_METRICS = "false"

## Incident 2: Data loss on DB pod restart
- Cause: emptyDir storage
- Fix: volumeClaimTemplates on ledger-db and accounts-db
- Lesson: Running != healthy; verify the data

## Known issues
- DB passwords in plaintext ConfigMaps
- Single DB replica (single point of failure)
- No backups yet

## Hardening (Trivy config scan)
- Before: KSV-0118 x4, KSV-0109 x3, KSV-0014 x2
- Done: DBs run as non-root (uid 70), data verified after restart
- Next: readOnlyRootFilesystem on DBs, then passwords to Secrets
- Accepted: DEMO_LOGIN_PASSWORD (public demo credential)

## Hardening results (Trivy config scan, HIGH/CRITICAL)
- Start: 9 findings (KSV-0118 x4, KSV-0109 x3, KSV-0014 x2)
- Now: 3 (KSV-0109, passwords in ConfigMaps)
- DBs: run as uid 70, readOnlyRootFilesystem, writable emptyDir only for /tmp and /var/run/postgresql
- Verified: data survives pod deletion with the hardened settings
- Known harmless log: chmod on /var/run/postgresql "Operation not permitted" (image startup script, fsGroup already makes it writable)
- Accepted: DEMO_LOGIN_PASSWORD (public demo credential)
- Remaining: move DB passwords into Secrets, including the copy inside ACCOUNTS_DB_URI

## Verified: database hardening
- ledger-db and accounts-db: non-root (uid 70), readOnlyRootFilesystem, PVC-backed
- Test: new writes survive pod deletion for both DBs
- Observed: balancereader/transactionhistory take a few minutes to recover after a DB restart (blank balance/history meanwhile)
- Improvement ideas: startup/readiness tuning, DB connection retry, DB replica

## Frontend image hardening
- Before: 31 HIGH/CRITICAL (3 CRITICAL). After: 1 HIGH (zlib1g, no fix in base yet)
- Fixes: base image digest update, uv.lock bump (certifi, pyasn1), pip removed from final image
- Lesson: pinned digests are reproducible but go stale; pip vendors its own libraries
- Accepted: zlib1g (revisit when base image updates)
- Known: Dockerfile pulls uv from ghcr.io/astral-sh/uv:latest (unpinned)

## Pipeline gate (frontend)
- build-frontend: build, Trivy report (HIGH+CRITICAL), Trivy gate (fail on fixable CRITICAL), push only on main
- Verified: PR #4 with an old lockfile failed at the gate and skipped the push
- Accepted: zlib1g HIGH (no fix in base image yet)