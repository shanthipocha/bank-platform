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