"""Hermes AI investigation integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from typing import Any

from config import get_config
from hermes_client import HermesClient, HermesError
from integrations.base import IntegrationMeta, IntegrationStatus


class HermesIntegration:
    meta = IntegrationMeta(
        id="hermes",
        name="Hermes",
        kind="investigate",
        description="Start AI investigations against incidents via the Hermes WebUI API.",
        config_group="hermes",
        enabled_key="hermes.enabled",
        field_keys=[
            "hermes.enabled",
            "hermes.webui_url",
            "hermes.webui_password",
            "hermes.workspace",
            "hermes.public_base_url",
            "hermes.webhook_url",
            "hermes.webhook_secret",
        ],
    )

    def is_enabled(self) -> bool:
        return get_config().get_bool(self.meta.enabled_key)

    def client(self) -> HermesClient:
        cfg = get_config()
        return HermesClient(
            base_url=cfg.get_str("hermes.webui_url"),
            password=cfg.get_str("hermes.webui_password"),
            workspace=cfg.get_str("hermes.workspace") or "/workspace",
        )

    def public_base_url(self) -> str:
        return get_config().get_str("hermes.public_base_url")

    def validate(self) -> IntegrationStatus:
        cfg = get_config()
        if not self.is_enabled():
            return IntegrationStatus(False, "Hermes integration is disabled")
        base = cfg.get_str("hermes.webui_url")
        if not base:
            return IntegrationStatus(False, "Hermes WebUI URL is not configured")
        try:
            if cfg.get_str("hermes.webui_password"):
                self.client()
                return IntegrationStatus(True, f"Authenticated to {base}")
            req = urllib.request.Request(base, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                return IntegrationStatus(
                    True,
                    f"Reachable (HTTP {resp.status}); set password to verify login",
                )
        except HermesError as exc:
            return IntegrationStatus(False, str(exc), detail=exc.detail)
        except urllib.error.URLError as exc:
            return IntegrationStatus(False, f"Hermes unreachable: {exc.reason}")
        except Exception as exc:
            return IntegrationStatus(False, str(exc))

    def forward_webhook(self, incident: dict[str, Any]) -> tuple[int, bytes]:
        cfg = get_config()
        secret = cfg.get_str("hermes.webhook_secret")
        url = cfg.get_str("hermes.webhook_url")
        if not secret or not url:
            return 503, b'{"error":"hermes webhook not configured"}'
        body = json.dumps(incident).encode("utf-8")
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            return 502, json.dumps(
                {"error": "hermes webhook unreachable", "detail": str(exc.reason)}
            ).encode("utf-8")
