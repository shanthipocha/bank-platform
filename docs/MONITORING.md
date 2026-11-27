# Monitoring, alerting and AIOps (kind; same files for EKS/GKE/AKS)

## Components
| Piece | What | Files |
|---|---|---|
| kube-prometheus-stack (Helm release `kps`, ns `monitoring`) | Prometheus, Grafana, Alertmanager, kube-state-metrics | `monitoring/kube-prometheus-values.yaml` |
| Alert routing | Slack by severity: critical -> #bank-alerts-critical, warning -> #bank-alerts-warning, Watchdog/InfoInhibitor dropped | `monitoring/alertmanager-values.yaml` |
| Bank alert rules | BankDatabaseDown (critical), BankPodCrashLooping (critical), BankServiceUnavailable (warning), BankHighRestartRate (warning) | `monitoring/bank-alerts.yaml` |
| AIOps assistant | Python stdlib service. Receives Bank* alerts by webhook, reads pod status, events and logs (read-only RBAC, ns default), posts context to Slack, optionally adds LLM analysis | `aiops/app.py`, `aiops/llm.py`, `aiops/aiops.yaml` |

## Alert flow
Prometheus rule fires -> Alertmanager (group_wait 30s) -> Slack (severity route) and, for `Bank*` alerts, also -> `http://aiops.monitoring.svc:8080/alert` (`continue: true`) -> AIOps posts context + AI analysis to the same severity channel. Alerts are deduplicated per fingerprint for 1 hour.

## Secrets (cluster only, never in git; recreate on every fresh cluster)
- `alertmanager-slack` (ns monitoring): `critical-url`, `warning-url` (Slack incoming webhooks)
- `aiops-llm` (ns monitoring): `LLM_PROVIDER` (none | openai | anthropic), `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`
- App secrets (default ns): `ledger-db-secret`, `accounts-db-secret`, `jwt-key`

## Install
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kps prometheus-community/kube-prometheus-stack -n monitoring --create-namespace \
  -f monitoring/kube-prometheus-values.yaml -f monitoring/alertmanager-values.yaml
kubectl apply -f monitoring/bank-alerts.yaml
# create the Secrets above, then:
kubectl create configmap aiops-code -n monitoring --from-file=aiops/app.py --from-file=aiops/llm.py
kubectl apply -f aiops/aiops.yaml
```
After editing `aiops/*.py`: recreate the configmap with `--dry-run=client -o yaml | kubectl apply -f -`, then `kubectl rollout restart deploy/aiops -n monitoring`.

## Switch the LLM (config only, no code change)
Free tier used so far: Gemini via the OpenAI-compatible endpoint (`gemini-2.5-flash`). Anthropic: `LLM_PROVIDER=anthropic` plus a Haiku-tier model id. Off: `LLM_PROVIDER=none`.

## Test
- Fake alert: POST a firing alert JSON to the aiops service (port-forward 8080), with a new fingerprint each time.
- Real outage: `kubectl scale statefulset/ledger-db --replicas=0`, wait ~3 min, then scale back to 1.

## Lessons
- Grafana needed 512Mi (256Mi was OOMKilled).
- Thinking models (Gemini 2.5) spend hidden tokens: `max_tokens` 300 truncated the answer, 1200 works.
- Slack message links use the in-cluster Alertmanager URL and will not open from a browser; set `externalUrl` when there is an ingress.
- A WSL/Docker restart restarts every pod at once. Not an app fault, and the AI analysis should say so.
- kind: etcd/scheduler/controller-manager/proxy/node-exporter scraping disabled (not exposed). Re-enable on real clouds.

## Known gaps
CPUThrottlingHigh is noisy on kind. No logs/traces backend yet (Loki, Tempo). AIOps is read-only; no auto-remediation. Webhook is unauthenticated inside the cluster (add a NetworkPolicy).
