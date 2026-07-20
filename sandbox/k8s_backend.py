"""Kubernetes backend: create ephemeral triage pods and talk to sandbox-agent."""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from typing import Any


class K8sError(RuntimeError):
    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.detail = detail


def _in_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST")) and os.path.isfile(
        "/var/run/secrets/kubernetes.io/serviceaccount/token"
    )


class K8sBackend:
    """Manage sandbox pods via the Kubernetes REST API (in-cluster SA)."""

    def __init__(
        self,
        *,
        namespace: str,
        image: str,
        service_account: str,
        agent_port: int = 8080,
        ttl_seconds: int = 3600,
        cpu_request: str = "50m",
        memory_request: str = "128Mi",
        memory_limit: str = "512Mi",
    ) -> None:
        self.namespace = namespace
        self.image = image
        self.service_account = service_account
        self.agent_port = agent_port
        self.ttl_seconds = ttl_seconds
        self.cpu_request = cpu_request
        self.memory_request = memory_request
        self.memory_limit = memory_limit
        self._token = ""
        self._ca = ""
        self._host = ""
        self._ssl_ctx: ssl.SSLContext | None = None
        if _in_cluster():
            self._load_in_cluster()

    def available(self) -> bool:
        return bool(self._token and self._host)

    def _load_in_cluster(self) -> None:
        with open("/var/run/secrets/kubernetes.io/serviceaccount/token", encoding="utf-8") as fh:
            self._token = fh.read().strip()
        self._ca = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        self._host = f"https://{host}:{port}"
        self._ssl_ctx = ssl.create_default_context(cafile=self._ca)

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if not self.available():
            raise K8sError("not running in-cluster (no service account)")
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(req, context=self._ssl_ctx, timeout=timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise K8sError(f"k8s {method} {path} failed: {exc.code}", detail=detail) from exc
        except urllib.error.URLError as exc:
            raise K8sError(f"k8s unreachable: {exc.reason}") from exc

    def pod_name(self, incident_id: str) -> str:
        safe = "".join(c if c.isalnum() or c in "-." else "-" for c in incident_id.lower())[:40]
        return f"hearth-sb-{safe}"[:63].rstrip("-")

    def ensure_pod(self, incident_id: str) -> dict[str, Any]:
        name = self.pod_name(incident_id)
        try:
            existing = self._request("GET", f"/api/v1/namespaces/{self.namespace}/pods/{name}")
            phase = ((existing.get("status") or {}).get("phase") or "").lower()
            if phase in ("pending", "running"):
                return self._wait_ready(name, existing)
            self.delete_pod(incident_id)
        except K8sError as exc:
            detail = str(exc.detail or "")
            if "404" not in str(exc) and "NotFound" not in detail:
                raise

        pod = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": self.namespace,
                "labels": {
                    "app.kubernetes.io/name": "hearth-sandbox",
                    "app.kubernetes.io/part-of": "hearth",
                    "hearth.nerd.dad/incident-id": incident_id,
                },
            },
            "spec": {
                "restartPolicy": "Never",
                "serviceAccountName": self.service_account,
                "automountServiceAccountToken": True,
                "containers": [
                    {
                        "name": "triage",
                        "image": self.image,
                        "imagePullPolicy": "IfNotPresent",
                        "ports": [{"name": "agent", "containerPort": self.agent_port}],
                        "readinessProbe": {
                            "httpGet": {"path": "/health", "port": self.agent_port},
                            "initialDelaySeconds": 1,
                            "periodSeconds": 2,
                        },
                        "resources": {
                            "requests": {
                                "cpu": self.cpu_request,
                                "memory": self.memory_request,
                            },
                            "limits": {"memory": self.memory_limit},
                        },
                        "workingDir": "/workspace",
                    }
                ],
            },
        }
        created = self._request("POST", f"/api/v1/namespaces/{self.namespace}/pods", body=pod)
        return self._wait_ready(name, created)

    def _wait_ready(self, name: str, pod: dict[str, Any], *, timeout: float = 90.0) -> dict[str, Any]:
        deadline = time.time() + timeout
        current = pod
        while time.time() < deadline:
            phase = ((current.get("status") or {}).get("phase") or "").lower()
            pod_ip = (current.get("status") or {}).get("podIP") or ""
            ready = False
            for cond in (current.get("status") or {}).get("conditions") or []:
                if cond.get("type") == "Ready" and str(cond.get("status")).lower() == "true":
                    ready = True
                    break
            if phase == "running" and pod_ip and ready:
                return {
                    "pod_name": name,
                    "namespace": self.namespace,
                    "pod_ip": pod_ip,
                    "agent_url": f"http://{pod_ip}:{self.agent_port}",
                    "phase": phase,
                }
            if phase in ("failed", "succeeded", "unknown"):
                raise K8sError(f"sandbox pod {name} in phase {phase}")
            time.sleep(1.5)
            current = self._request("GET", f"/api/v1/namespaces/{self.namespace}/pods/{name}")
        raise K8sError(f"sandbox pod {name} not ready within {timeout}s")

    def delete_pod(self, incident_id: str) -> None:
        name = self.pod_name(incident_id)
        try:
            self._request(
                "DELETE",
                f"/api/v1/namespaces/{self.namespace}/pods/{name}?gracePeriodSeconds=5",
            )
        except K8sError as exc:
            if "404" in str(exc) or "NotFound" in str(exc.detail or ""):
                return
            raise

    def agent_exec(self, agent_url: str, command: str, *, timeout: float = 120.0) -> dict[str, Any]:
        payload = json.dumps({"command": command, "timeout": timeout}).encode("utf-8")
        req = urllib.request.Request(
            f"{agent_url.rstrip('/')}/exec",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            try:
                return json.loads(detail)
            except json.JSONDecodeError:
                raise K8sError(f"sandbox exec failed: {exc.code}", detail=detail) from exc
        except urllib.error.URLError as exc:
            raise K8sError(f"sandbox agent unreachable: {exc.reason}") from exc
