## Incident 1: CrashLoopBackOff on all app pods (local kind)
- Symptom: all app pods CrashLoopBackOff, DBs healthy
- Investigation: describe pod, logs --previous, ruled out memory and JWT secret
- Root cause: tracing integration required GCP credentials not present locally
- Fix: ENABLE_TRACING / ENABLE_METRICS = false in manifests
- Lesson: read stack traces bottom-up; check for drift between cluster and git
- Detection idea: alert on pod restart count > 3 in 10 min