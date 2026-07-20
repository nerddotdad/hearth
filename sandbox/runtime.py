"""Sandbox lifecycle facade used by bridge, investigate, and MCP."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from sandbox import audit
from sandbox.k8s_backend import K8sBackend, K8sError
from sandbox.local_backend import LocalBackend
from sandbox.tokens import hash_token, issue_token, sandbox_record_from_enrichment, token_matches

_SERVICE: "SandboxService | None" = None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def utcnow_iso() -> str:
    return utcnow().isoformat()


class SandboxService:
    def __init__(self, store: Any, config: Any) -> None:
        self.store = store
        self.config = config
        self._lock = threading.RLock()
        self._backend: Any | None = None

    def enabled(self) -> bool:
        return bool(self.config.get_bool("sandbox.enabled"))

    def backend_name(self) -> str:
        return (self.config.get_str("sandbox.backend") or "auto").strip().lower() or "auto"

    def _get_backend(self) -> Any:
        if self._backend is not None:
            return self._backend
        name = self.backend_name()
        if name == "local":
            self._backend = LocalBackend()
            return self._backend
        k8s = K8sBackend(
            namespace=self.config.get_str("sandbox.namespace") or "hearth-sandboxes",
            image=self.config.get_str("sandbox.image") or "ghcr.io/nerddotdad/hearth-sandbox:0.1.0",
            service_account=self.config.get_str("sandbox.service_account") or "hearth-sandbox",
            agent_port=int(self.config.get_int("sandbox.agent_port") or 8080),
            ttl_seconds=int(self.config.get_int("sandbox.ttl_seconds") or 3600),
        )
        if name == "kubernetes" or (name == "auto" and k8s.available()):
            self._backend = k8s
            return self._backend
        self._backend = LocalBackend()
        return self._backend

    def tool_packs(self) -> list[str]:
        raw = self.config.get("sandbox.tool_packs")
        if isinstance(raw, list) and raw:
            return [str(x) for x in raw]
        return ["shell", "k8s-readonly", "network"]

    def public_mcp_url(self, incident_id: str) -> str | None:
        base = (self.config.get_str("sandbox.public_base_url") or "").rstrip("/")
        if not base:
            base = (self.config.get_str("core.incidents_public_base_url") or "").rstrip("/")
        if not base:
            return None
        return f"{base}/mcp"

    def status(self, incident_id: str) -> dict[str, Any] | None:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        rec = sandbox_record_from_enrichment(incident.get("enrichment"))
        if not rec:
            return {
                "incident_id": incident_id,
                "status": "absent",
                "enabled": self.enabled(),
                "tool_packs": self.tool_packs(),
            }
        expired = False
        expires_at = str(rec.get("expires_at") or "")
        if expires_at:
            try:
                exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                expired = utcnow() >= exp
            except ValueError:
                expired = False
        return {
            "incident_id": incident_id,
            "status": "expired" if expired else str(rec.get("status") or "unknown"),
            "pod_name": rec.get("pod_name"),
            "namespace": rec.get("namespace"),
            "backend": rec.get("backend"),
            "created_at": rec.get("created_at"),
            "expires_at": rec.get("expires_at"),
            "last_used_at": rec.get("last_used_at"),
            "tool_packs": self.tool_packs(),
            "mcp_url": self.public_mcp_url(incident_id),
            "terminal_path": f"/api/incidents/{incident_id}/sandbox/terminal",
            "enabled": self.enabled(),
        }

    def ensure(
        self,
        incident_id: str,
        *,
        actor: str = "api",
        rotate_token: bool = False,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("sandbox is disabled")
        with self._lock:
            incident = self.store.get_incident(incident_id)
            if incident is None:
                raise ValueError("incident not found")
            enrichment = dict(incident.get("enrichment") or {})
            rec = sandbox_record_from_enrichment(enrichment)
            token: str | None = None

            # Reuse healthy non-expired sandbox
            if rec.get("status") == "ready" and not rotate_token:
                expires_at = str(rec.get("expires_at") or "")
                still_valid = True
                if expires_at:
                    try:
                        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                        if exp.tzinfo is None:
                            exp = exp.replace(tzinfo=timezone.utc)
                        still_valid = utcnow() < exp
                    except ValueError:
                        still_valid = True
                if still_valid and rec.get("agent_url"):
                    # touch TTL
                    ttl = int(self.config.get_int("sandbox.ttl_seconds") or 3600)
                    rec["expires_at"] = (utcnow() + timedelta(seconds=ttl)).isoformat()
                    rec["last_used_at"] = utcnow_iso()
                    enrichment["sandbox"] = rec
                    self.store.update_incident(incident_id, enrichment=enrichment)
                    out = self.status(incident_id) or {}
                    out["token"] = None  # not re-issued
                    out["agent_url"] = rec.get("agent_url")
                    return out

            backend = self._get_backend()
            info = backend.ensure_pod(incident_id)
            ttl = int(self.config.get_int("sandbox.ttl_seconds") or 3600)
            if rotate_token or not rec.get("token_hash"):
                token = issue_token()
                token_hash = hash_token(token)
            else:
                token_hash = str(rec.get("token_hash") or "")
                token = None

            new_rec = {
                "status": "ready",
                "pod_name": info.get("pod_name"),
                "namespace": info.get("namespace"),
                "pod_ip": info.get("pod_ip"),
                "agent_url": info.get("agent_url"),
                "backend": info.get("backend") or self.backend_name(),
                "token_hash": token_hash,
                "created_at": rec.get("created_at") or utcnow_iso(),
                "expires_at": (utcnow() + timedelta(seconds=ttl)).isoformat(),
                "last_used_at": utcnow_iso(),
                "started_by": actor,
            }
            enrichment["sandbox"] = new_rec
            self.store.update_incident(
                incident_id,
                enrichment=enrichment,
                actor=actor,
                event_type="sandbox_started",
                event_detail={"pod_name": new_rec["pod_name"], "backend": new_rec["backend"]},
            )
            out = self.status(incident_id) or {}
            out["token"] = token
            out["agent_url"] = new_rec["agent_url"]
            return out

    def destroy(self, incident_id: str, *, actor: str = "api") -> dict[str, Any]:
        with self._lock:
            incident = self.store.get_incident(incident_id)
            if incident is None:
                raise ValueError("incident not found")
            enrichment = dict(incident.get("enrichment") or {})
            rec = sandbox_record_from_enrichment(enrichment)
            if rec:
                try:
                    self._get_backend().delete_pod(incident_id)
                except K8sError:
                    pass
            enrichment.pop("sandbox", None)
            self.store.update_incident(
                incident_id,
                enrichment=enrichment,
                actor=actor,
                event_type="sandbox_destroyed",
                event_detail={"pod_name": rec.get("pod_name") if rec else None},
            )
            return {"incident_id": incident_id, "status": "absent"}

    def destroy_if_present(self, incident_id: str, *, actor: str = "system") -> None:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return
        if sandbox_record_from_enrichment(incident.get("enrichment")):
            try:
                self.destroy(incident_id, actor=actor)
            except Exception:
                pass

    def verify_token(self, incident_id: str, token: str) -> bool:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return False
        rec = sandbox_record_from_enrichment(incident.get("enrichment"))
        return token_matches(token, str(rec.get("token_hash") or ""))

    def _touch(self, incident_id: str, rec: dict[str, Any], enrichment: dict[str, Any]) -> None:
        ttl = int(self.config.get_int("sandbox.ttl_seconds") or 3600)
        rec["last_used_at"] = utcnow_iso()
        rec["expires_at"] = (utcnow() + timedelta(seconds=ttl)).isoformat()
        enrichment["sandbox"] = rec
        self.store.update_incident(incident_id, enrichment=enrichment)

    def exec_command(
        self,
        incident_id: str,
        command: str,
        *,
        actor: str = "api",
        timeout: float = 120.0,
        ensure: bool = True,
    ) -> dict[str, Any]:
        if not self.enabled():
            raise RuntimeError("sandbox is disabled")
        command = str(command or "").strip()
        if not command:
            raise ValueError("command required")
        with self._lock:
            if ensure:
                self.ensure(incident_id, actor=actor)
            incident = self.store.get_incident(incident_id)
            if incident is None:
                raise ValueError("incident not found")
            enrichment = dict(incident.get("enrichment") or {})
            rec = sandbox_record_from_enrichment(enrichment)
            agent_url = str(rec.get("agent_url") or "")
            if not agent_url:
                raise RuntimeError("sandbox not ready")
            backend = self._get_backend()
            result = backend.agent_exec(agent_url, command, timeout=timeout)
            self._touch(incident_id, rec, enrichment)
            audit.log_exec(
                incident_id=incident_id,
                actor=actor,
                command=command,
                exit_code=result.get("exit_code") if isinstance(result, dict) else None,
            )
            return result if isinstance(result, dict) else {"ok": False, "error": "bad result"}

    def agent_url(self, incident_id: str) -> str | None:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        rec = sandbox_record_from_enrichment(incident.get("enrichment"))
        url = str(rec.get("agent_url") or "")
        return url or None

    def attach_context(self, incident_id: str, *, actor: str = "investigate") -> dict[str, Any]:
        """Ensure sandbox and return non-secret MCP attach hints for agent prompts.

        Credentials must never appear in chat — agents authenticate via MCP client
        env (HEARTH_SANDBOX_AGENT_API_KEY) configured out-of-band.
        """
        self.ensure(incident_id, actor=actor, rotate_token=False)
        mcp_url = self.public_mcp_url(incident_id)
        cluster_url = (self.config.get_str("sandbox.cluster_base_url") or "").rstrip("/")
        if cluster_url:
            mcp_url = f"{cluster_url}/mcp"
        return {
            "mcp_url": mcp_url,
            "incident_id": incident_id,
            "tool_packs": self.tool_packs(),
            "instructions": (
                "Use Hearth MCP tools (sandbox_exec, sandbox_status, sandbox_ensure) "
                "for cluster triage. Prefer read-only kubectl/flux. Do not mutate the "
                "live cluster. Authenticate with your MCP client Authorization header "
                "from environment — never put API keys or bearer tokens in chat."
            ),
        }


def get_sandbox_service() -> SandboxService:
    if _SERVICE is None:
        raise RuntimeError("sandbox service not initialized")
    return _SERVICE


def init_sandbox_service(store: Any, config: Any) -> SandboxService:
    global _SERVICE
    _SERVICE = SandboxService(store, config)
    return _SERVICE
