# ELK (ECK + Fluent Bit) on kind: notes (2026-11-27)

Goal: compare ELK with Loki as the log layer (my org uses ELK).

## 1. Prep
- WSL memory was the limit (7.6 GB cap, about 3 GB free). Raised to 9 GB via `.wslconfig` for the session.
- Stopped Loki and Alloy, scaled loadgenerator to 0 during install.

## 2. Install (namespace `logging`)
- Helm repos: `elastic`, `fluent`.
- ECK operator (`elastic/eck-operator` 3.5.0) in `elastic-system`.
- `monitoring/elk/elastic-stack.yaml`: Elasticsearch 9.2.0 (single node, 5Gi PVC, `node.store.allow_mmap: false` for kind) and Kibana.
- `monitoring/elk/fluent-bit-values.yaml`: DaemonSet shipping pod logs to Elasticsearch over TLS, index `bank-logs-YYYY.MM.DD`, password read from the ECK secret.
- Dry-render with `helm template` before installing.

## 3. Problems and fixes
| Problem | Cause | Fix |
|---|---|---|
| Slow startup (7+ min) | 760 MB image pull | Waited |
| Kibana 500 errors | Elasticsearch OOMKilled (1Gi limit, 512m heap) | Heap 768m, limit 1536Mi |
| `kubectl scale` on Kibana ineffective | ECK owns the Deployment | Use `count` in the Kibana CR |
| sed also raised Kibana's limit | Over-broad pattern | Reset to 1Gi |
| Label field name | `Replace_Dots On` | Field is `kubernetes.labels.app` |

## 4. Verified
- Elasticsearch yellow/green (yellow is normal on one node), restart count 0 after the fix.
- Kibana data view `bank-logs-*`. Searches `kubernetes.labels.app : "frontend"` and `"balancereader"` return bank logs.
- `log_level : "error"` also showed the ECK operator logging Elasticsearch's own restart.

## 5. Loki vs ELK
| | Loki + Alloy | ELK |
|---|---|---|
| Memory | about 0.7 GB | about 2.5 GB |
| Setup | 2 charts | operator, CRDs, ES, Kibana, Fluent Bit, auth |
| Query | LogQL | KQL, full text |
| UI | Grafana (shared with metrics) | Kibana (separate) |

## 6. Access and teardown
- Password: `kubectl get secret elasticsearch-es-elastic-user -n logging -o go-template='{{.data.elastic | base64decode}}'` (never commit it).
- Kibana: `kubectl port-forward -n logging svc/kibana-kb-http 5601:5601`, open https://localhost:5601, user `elastic`.
- Teardown: `helm uninstall fb -n logging`, `kubectl delete -f monitoring/elk/elastic-stack.yaml`, `helm uninstall eck -n elastic-system`, `kubectl delete pvc --all -n logging`.
- Revert `.wslconfig` to get the RAM back.
