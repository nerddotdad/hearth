"""Minimal MCP Streamable HTTP server for Hearth sandbox tools."""

from __future__ import annotations

import json
from typing import Any, Callable

from sandbox.runtime import SandboxService


TOOLS = [
    {
        "name": "sandbox_status",
        "description": "Get triage sandbox status for an incident (pod, TTL, tool packs).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string", "description": "Hearth incident id"},
            },
            "required": ["incident_id"],
        },
    },
    {
        "name": "sandbox_ensure",
        "description": "Ensure the incident triage sandbox is running (creates pod if needed).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
            },
            "required": ["incident_id"],
        },
    },
    {
        "name": "sandbox_exec",
        "description": (
            "Run a non-interactive shell command in the incident triage sandbox "
            "(kubectl, flux, jq, curl, etc.). Read-only cluster access."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "incident_id": {"type": "string"},
                "command": {"type": "string", "description": "Shell command to run"},
                "timeout": {"type": "number", "description": "Seconds (default 120)"},
            },
            "required": ["incident_id", "command"],
        },
    },
]


class McpHandler:
    def __init__(
        self,
        sandbox: SandboxService,
        *,
        resolve_incident: Callable[[str | None, str | None], str | None] | None = None,
    ) -> None:
        self.sandbox = sandbox
        self.resolve_incident = resolve_incident

    def handle(
        self,
        payload: dict[str, Any],
        *,
        bearer_token: str | None = None,
        default_incident_id: str | None = None,
    ) -> dict[str, Any]:
        method = str(payload.get("method") or "")
        req_id = payload.get("id")
        params = payload.get("params") if isinstance(payload.get("params"), dict) else {}

        if method == "initialize":
            return self._result(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "hearth-sandbox", "version": "1.0.0"},
                },
            )
        if method == "notifications/initialized":
            return {"jsonrpc": "2.0", "result": {}}
        if method == "tools/list":
            return self._result(req_id, {"tools": TOOLS})
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            try:
                text = self._call_tool(
                    name,
                    arguments,
                    bearer_token=bearer_token,
                    default_incident_id=default_incident_id,
                )
                return self._result(
                    req_id,
                    {"content": [{"type": "text", "text": text}], "isError": False},
                )
            except Exception as exc:
                return self._result(
                    req_id,
                    {"content": [{"type": "text", "text": str(exc)}], "isError": True},
                )
        if method == "ping":
            return self._result(req_id, {})
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        bearer_token: str | None,
        default_incident_id: str | None,
    ) -> str:
        incident_id = str(arguments.get("incident_id") or default_incident_id or "").strip()
        if not incident_id:
            raise ValueError("incident_id required")
        if bearer_token:
            # Global agent key OR incident token
            global_key = self.sandbox.config.get_str("sandbox.agent_api_key")
            ok = False
            if global_key and bearer_token == global_key:
                ok = True
            elif self.sandbox.verify_token(incident_id, bearer_token):
                ok = True
            if not ok:
                raise PermissionError("invalid sandbox token")
        else:
            # Allow unauthenticated only when no tokens configured (local dev)
            global_key = self.sandbox.config.get_str("sandbox.agent_api_key")
            rec = self.sandbox.status(incident_id)
            # still require that sandbox exists or global key unset and local backend
            if global_key:
                raise PermissionError("authorization required")

        if name == "sandbox_status":
            return json.dumps(self.sandbox.status(incident_id) or {}, indent=2)
        if name == "sandbox_ensure":
            out = self.sandbox.ensure(incident_id, actor="mcp")
            safe = {k: v for k, v in out.items() if k != "token"}
            return json.dumps(safe, indent=2)
        if name == "sandbox_exec":
            command = str(arguments.get("command") or "")
            try:
                timeout = float(arguments.get("timeout") or 120)
            except (TypeError, ValueError):
                timeout = 120.0
            result = self.sandbox.exec_command(
                incident_id,
                command,
                actor="mcp",
                timeout=timeout,
                ensure=True,
            )
            return json.dumps(result, indent=2)
        raise ValueError(f"unknown tool: {name}")

    @staticmethod
    def _result(req_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}
