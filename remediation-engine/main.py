import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("remediation-engine")

MAX_REPLICAS = int(os.getenv("MAX_REPLICAS", "5"))
SCALE_UP_ALERTS = {"HighMemoryUsage", "HighSimulatedMemory", "HighErrorRate"}
RESTART_ALERTS = {"PodCrashLooping"}


class AlertItem(BaseModel):
    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None


class AlertmanagerPayload(BaseModel):
    receiver: str | None = None
    status: str = "firing"
    alerts: list[AlertItem] = Field(default_factory=list)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)


def get_apps_v1_client() -> client.AppsV1Api:
    """Initialize a Kubernetes AppsV1Api client (in-cluster with kubeconfig fallback)."""
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.AppsV1Api()


def scale_up_deployment(
    apps_v1: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
    max_replicas: int = MAX_REPLICAS,
) -> dict[str, Any]:
    """Scale a Deployment up by 1 replica, capped at max_replicas."""
    deployment = apps_v1.read_namespaced_deployment(
        name=deployment_name,
        namespace=namespace,
    )
    current_replicas = deployment.spec.replicas if deployment.spec.replicas is not None else 1

    if current_replicas >= max_replicas:
        return {
            "action": "scale_skipped_at_limit",
            "namespace": namespace,
            "deployment": deployment_name,
            "previous_replicas": current_replicas,
            "new_replicas": current_replicas,
            "detail": f"Deployment already at max replica cap ({max_replicas}).",
        }

    target_replicas = min(current_replicas + 1, max_replicas)
    apps_v1.patch_namespaced_deployment(
        name=deployment_name,
        namespace=namespace,
        body={"spec": {"replicas": target_replicas}},
    )
    return {
        "action": "scaled_up",
        "namespace": namespace,
        "deployment": deployment_name,
        "previous_replicas": current_replicas,
        "new_replicas": target_replicas,
        "detail": f"Scaled {namespace}/{deployment_name} from {current_replicas} to {target_replicas} replicas.",
    }


def rolling_restart_deployment(
    apps_v1: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
) -> dict[str, Any]:
    """Trigger a rolling restart of a Deployment via restartedAt annotation."""
    restarted_at = datetime.now(timezone.utc).isoformat()
    patch_body = {
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "kubectl.kubernetes.io/restartedAt": restarted_at,
                    }
                }
            }
        }
    }
    apps_v1.patch_namespaced_deployment(
        name=deployment_name,
        namespace=namespace,
        body=patch_body,
    )
    return {
        "action": "rolling_restart",
        "namespace": namespace,
        "deployment": deployment_name,
        "restarted_at": restarted_at,
        "detail": f"Triggered rolling restart for {namespace}/{deployment_name}.",
    }


def format_incident_report(
    alert: AlertItem,
    remediation: dict[str, Any],
) -> str:
    """Format a structured SRE incident & remediation summary."""
    alertname = alert.labels.get("alertname", "UnknownAlert")
    namespace = alert.labels.get("namespace", "unknown")
    deployment = alert.labels.get("deployment", "unknown")
    severity = alert.labels.get("severity", "warning")
    summary = alert.annotations.get("summary") or alert.annotations.get("description") or "No summary provided"

    lines = [
        "SRE Auto-Remediation Report",
        f"Alert: {alertname} ({alert.status.upper()})",
        f"Severity: {severity}",
        f"Target: {namespace}/{deployment}",
        f"Summary: {summary}",
        f"Action: {remediation.get('action')}",
        f"Outcome: {remediation.get('detail')}",
    ]
    return "\n".join(lines)


async def send_telegram_notification(message: str) -> bool:
    """Send report to Telegram Bot API, or log cleanly to console if unconfigured."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not token or not chat_id:
        logger.info("Telegram credentials not configured; logging report to console:\n%s", message)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.post(url, json=payload)
            response.raise_for_status()
        logger.info("Sent incident report to Telegram chat %s", chat_id)
        return True
    except httpx.HTTPError as exc:
        logger.error("Failed to deliver Telegram notification (%s); fallback report:\n%s", exc, message)
        return False


def remediate_alert(alert: AlertItem, apps_v1: client.AppsV1Api | None = None) -> dict[str, Any]:
    """Evaluate a single Alertmanager alert and perform Kubernetes remediation if firing."""
    alertname = alert.labels.get("alertname", "UnknownAlert")
    namespace = alert.labels.get("namespace")
    deployment = alert.labels.get("deployment")

    if alert.status.lower() != "firing":
        return {
            "action": "ignored_non_firing",
            "alertname": alertname,
            "detail": f"Alert status is '{alert.status}'; no remediation needed.",
        }

    if not namespace or not deployment:
        return {
            "action": "skipped_missing_labels",
            "alertname": alertname,
            "detail": "Missing required 'namespace' or 'deployment' label on alert.",
        }

    k8s_client = apps_v1 or get_apps_v1_client()

    try:
        if alertname in SCALE_UP_ALERTS:
            return scale_up_deployment(k8s_client, namespace, deployment)
        if alertname in RESTART_ALERTS:
            return rolling_restart_deployment(k8s_client, namespace, deployment)
        return {
            "action": "no_automated_playbook",
            "alertname": alertname,
            "namespace": namespace,
            "deployment": deployment,
            "detail": f"No automated remediation playbook configured for '{alertname}'.",
        }
    except ApiException as exc:
        logger.exception("Kubernetes API error remediating %s/%s", namespace, deployment)
        return {
            "action": "remediation_failed",
            "alertname": alertname,
            "namespace": namespace,
            "deployment": deployment,
            "detail": f"Kubernetes API error ({exc.status}): {exc.reason}",
        }


app = FastAPI(
    title="Self-Healing Remediation Engine",
    version="0.1.0",
)


@app.get("/health", tags=["probes"])
def health() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "healthy"}


@app.get("/ready", tags=["probes"])
def ready() -> dict[str, str]:
    """Readiness probe endpoint."""
    return {"status": "ready"}


@app.post("/webhook", tags=["alertmanager"])
async def alertmanager_webhook(payload: AlertmanagerPayload) -> dict[str, Any]:
    """Receive Alertmanager webhooks, run Kubernetes remediation, and notify."""
    results: list[dict[str, Any]] = []
    apps_v1: client.AppsV1Api | None = None

    for alert in payload.alerts:
        if alert.status.lower() == "firing" and apps_v1 is None:
            try:
                apps_v1 = get_apps_v1_client()
            except Exception as exc:
                logger.error("Unable to initialize Kubernetes client: %s", exc)
                result = {
                    "action": "k8s_client_error",
                    "alertname": alert.labels.get("alertname", "UnknownAlert"),
                    "detail": f"Failed to initialize Kubernetes client: {exc}",
                }
                report = format_incident_report(alert, result)
                await send_telegram_notification(report)
                results.append(result)
                continue

        result = remediate_alert(alert, apps_v1=apps_v1)
        results.append(result)

        if alert.status.lower() == "firing":
            report = format_incident_report(alert, result)
            await send_telegram_notification(report)
        else:
            logger.info("Alert %s resolved; skipping remediation.", alert.labels.get("alertname"))

    return {
        "status": "processed",
        "alerts_received": len(payload.alerts),
        "results": results,
    }
