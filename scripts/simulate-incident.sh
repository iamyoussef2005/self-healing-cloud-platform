#!/usr/bin/env bash
set -euo pipefail

CLUSTER_CONTEXT="${CLUSTER_CONTEXT:-kind-self-healing-cluster}"
APP_NAMESPACE="${APP_NAMESPACE:-app}"
HEALING_NAMESPACE="${HEALING_NAMESPACE:-self-healing}"
BACKEND_DEPLOYMENT="${BACKEND_DEPLOYMENT:-demo-app-backend}"
BACKEND_SERVICE="${BACKEND_SERVICE:-demo-app-backend}"
LOCAL_PORT="${LOCAL_PORT:-18000}"
CHAOS_MB="${CHAOS_MB:-512}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-180}"
POLL_INTERVAL="${POLL_INTERVAL:-5}"

PF_PID=""
LOGS_PID=""

cleanup() {
  if [[ -n "${LOGS_PID}" ]] && kill -0 "${LOGS_PID}" 2>/dev/null; then
    kill "${LOGS_PID}" 2>/dev/null || true
  fi
  if [[ -n "${PF_PID}" ]] && kill -0 "${PF_PID}" 2>/dev/null; then
    kill "${PF_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

for cmd in kubectl curl; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "ERROR: '${cmd}' is required but not installed." >&2
    exit 1
  fi
done

echo "==> Checking initial replica count for ${APP_NAMESPACE}/${BACKEND_DEPLOYMENT}..."
INITIAL_REPLICAS="$(kubectl --context "${CLUSTER_CONTEXT}" -n "${APP_NAMESPACE}" \
  get deployment "${BACKEND_DEPLOYMENT}" -o jsonpath='{.spec.replicas}')"
INITIAL_REPLICAS="${INITIAL_REPLICAS:-1}"
echo "Initial desired replicas: ${INITIAL_REPLICAS}"

echo "==> Starting port-forward to svc/${BACKEND_SERVICE} on localhost:${LOCAL_PORT}..."
kubectl --context "${CLUSTER_CONTEXT}" -n "${APP_NAMESPACE}" \
  port-forward "svc/${BACKEND_SERVICE}" "${LOCAL_PORT}:8000" >/tmp/demo-app-pf.log 2>&1 &
PF_PID=$!

echo "==> Waiting for backend /health endpoint..."
for _ in $(seq 1 20); do
  if curl -fsS "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:${LOCAL_PORT}/health" >/dev/null 2>&1; then
  echo "ERROR: Backend did not become reachable via port-forward." >&2
  cat /tmp/demo-app-pf.log >&2 || true
  exit 1
fi

echo "==> Triggering memory chaos (${CHAOS_MB} MB > 400 MB alert threshold)..."
CHAOS_RESPONSE="$(curl -fsS -X POST "http://127.0.0.1:${LOCAL_PORT}/chaos/memory?mb=${CHAOS_MB}&allocate=false")"
echo "Chaos response: ${CHAOS_RESPONSE}"

echo "==> Tailing remediation-engine logs in namespace '${HEALING_NAMESPACE}'..."
kubectl --context "${CLUSTER_CONTEXT}" -n "${HEALING_NAMESPACE}" \
  logs -l app.kubernetes.io/name=remediation-engine -f --tail=20 --prefix=true &
LOGS_PID=$!

echo "==> Waiting up to ${TIMEOUT_SECONDS}s for Prometheus -> Alertmanager -> Remediation Engine to scale ${BACKEND_DEPLOYMENT}..."
DEADLINE=$((SECONDS + TIMEOUT_SECONDS))
SCALED=false

while (( SECONDS < DEADLINE )); do
  CURRENT_REPLICAS="$(kubectl --context "${CLUSTER_CONTEXT}" -n "${APP_NAMESPACE}" \
    get deployment "${BACKEND_DEPLOYMENT}" -o jsonpath='{.spec.replicas}')"
  READY_REPLICAS="$(kubectl --context "${CLUSTER_CONTEXT}" -n "${APP_NAMESPACE}" \
    get deployment "${BACKEND_DEPLOYMENT}" -o jsonpath='{.status.readyReplicas}')"
  READY_REPLICAS="${READY_REPLICAS:-0}"

  if (( CURRENT_REPLICAS > INITIAL_REPLICAS )); then
    echo ""
    echo "==> SUCCESS: Deployment ${BACKEND_DEPLOYMENT} auto-scaled from ${INITIAL_REPLICAS} to ${CURRENT_REPLICAS} desired replicas (${READY_REPLICAS} ready)."
    SCALED=true
    break
  fi

  sleep "${POLL_INTERVAL}"
done

if [[ "${SCALED}" != "true" ]]; then
  echo ""
  echo "ERROR: Timed out after ${TIMEOUT_SECONDS}s waiting for ${BACKEND_DEPLOYMENT} to scale above ${INITIAL_REPLICAS}." >&2
  exit 1
fi
