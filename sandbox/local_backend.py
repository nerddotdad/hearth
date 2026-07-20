"""Local sandbox backend for development (no Kubernetes)."""

from __future__ import annotations

import os
import subprocess
from typing import Any


class LocalBackend:
    """Run triage commands on the Hearth host process (dev / non-cluster)."""

    def available(self) -> bool:
        return True

    def ensure_pod(self, incident_id: str) -> dict[str, Any]:
        return {
            "pod_name": f"local-{incident_id}",
            "namespace": "local",
            "pod_ip": "127.0.0.1",
            "agent_url": "local://",
            "phase": "running",
            "backend": "local",
        }

    def delete_pod(self, incident_id: str) -> None:
        return None

    def agent_exec(self, agent_url: str, command: str, *, timeout: float = 120.0) -> dict[str, Any]:
        try:
            proc = subprocess.run(
                ["/bin/bash", "-lc", command],
                capture_output=True,
                timeout=max(1.0, min(timeout, 600.0)),
                env=os.environ.copy(),
            )
            return {
                "ok": True,
                "exit_code": proc.returncode,
                "stdout": proc.stdout.decode("utf-8", errors="replace")[:2 * 1024 * 1024],
                "stderr": proc.stderr.decode("utf-8", errors="replace")[:2 * 1024 * 1024],
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": "command timed out", "exit_code": -1, "stdout": "", "stderr": ""}
        except OSError as exc:
            return {"ok": False, "error": str(exc), "exit_code": -1, "stdout": "", "stderr": ""}
