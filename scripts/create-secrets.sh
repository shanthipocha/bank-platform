#!/usr/bin/env bash
# Creates all cluster-only Secrets. Usage: scripts/create-secrets.sh <expected-context-substring>
# Optional env: LEDGER_DB_PASSWORD, ACCOUNTS_DB_PASSWORD (defaults are demo values)
# Slack/LLM secrets are only created if SLACK_CRIT_URL / SLACK_WARN_URL are set (else prompted with -s).
set -euo pipefail
want="${1:?usage: $0 <context-substring, e.g. kind-bank or bank-eks>}"
ctx=$(kubectl config current-context)
case "$ctx" in *"$want"*) ;; *) echo "Context is '$ctx', expected it to contain '$want'. Aborting."; exit 1;; esac
echo "Context: $ctx"

LP="${LEDGER_DB_PASSWORD:-password}"
AP="${ACCOUNTS_DB_PASSWORD:-accounts-pwd}"

apply() { kubectl apply -f -; }

kubectl create secret generic ledger-db-secret \
  --from-literal=POSTGRES_PASSWORD="$LP" \
  --from-literal=SPRING_DATASOURCE_PASSWORD="$LP" --dry-run=client -o yaml | apply
kubectl create secret generic accounts-db-secret \
  --from-literal=POSTGRES_PASSWORD="$AP" \
  --from-literal=ACCOUNTS_DB_URI="postgresql://accounts-admin:${AP}@accounts-db:5432/accounts-db" --dry-run=client -o yaml | apply

if ! kubectl get secret jwt-key >/dev/null 2>&1; then
  d=$(mktemp -d); trap 'rm -rf "$d"' EXIT
  openssl genrsa -out "$d/jwtRS256.key" 4096 2>/dev/null
  openssl rsa -in "$d/jwtRS256.key" -pubout -out "$d/jwtRS256.key.pub" 2>/dev/null
  kubectl create secret generic jwt-key --from-file="$d/jwtRS256.key" --from-file="$d/jwtRS256.key.pub"
else echo "jwt-key exists, keeping it"; fi

if kubectl get ns monitoring >/dev/null 2>&1; then
  [ -n "${SLACK_CRIT_URL:-}" ] || read -s -p "Slack critical webhook URL (Enter to skip monitoring secrets): " SLACK_CRIT_URL; echo
  if [ -n "${SLACK_CRIT_URL:-}" ]; then
    [ -n "${SLACK_WARN_URL:-}" ] || read -s -p "Slack warning webhook URL: " SLACK_WARN_URL; echo
    kubectl create secret generic alertmanager-slack -n monitoring \
      --from-literal=critical-url="$SLACK_CRIT_URL" --from-literal=warning-url="$SLACK_WARN_URL" --dry-run=client -o yaml | apply
    kubectl get secret aiops-llm -n monitoring >/dev/null 2>&1 || \
      kubectl create secret generic aiops-llm -n monitoring --from-literal=LLM_PROVIDER=none
  fi
else echo "No monitoring namespace yet: re-run after installing the monitoring stack to create Slack/LLM secrets."; fi
echo "Done."
