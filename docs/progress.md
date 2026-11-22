## Incident 1: CrashLoopBackOff on all app pods (local kind)
- Symptom: all app pods CrashLoopBackOff, DBs healthy
- Investigation: describe pod, logs --previous, ruled out memory and JWT secret
- Root cause: tracing integration required GCP credentials not present locally
- Fix: ENABLE_TRACING / ENABLE_METRICS = false in manifests
- Lesson: read stack traces bottom-up; check for drift between cluster and git
- Detection idea: alert on pod restart count > 3 in 10 min

## Incident 3: Data loss on ledger-db pod restart
- Symptom: transactions missing after pod deleted and recreated
- Cause: DB storage was emptyDir (ephemeral)
- Impact: all user transactions lost (RPO violated)
- Fix: persistent volume via volumeClaimTemplates
- Lesson: Running != healthy; verify data, not just pod state
- Prevention: persistent storage, backups, restore test, reconciliation check