"""Prometheus / Alertmanager webhook ingest integration."""

from __future__ import annotations

from typing import Any

from config import get_config
from integrations.base import IntegrationMeta, IntegrationStatus


class PrometheusIntegration:
    meta = IntegrationMeta(
        id="prometheus",
        name="Prometheus",
        kind="ingest",
        description="Ingest Alertmanager (and Grafana) webhook payloads into the alerts inbox.",
        config_group="prometheus",
        enabled_key="prometheus.enabled",
        field_keys=[
            "prometheus.enabled",
            "prometheus.ignored_alertnames",
            "prometheus.ignored_alert_rules",
        ],
    )

    def is_enabled(self) -> bool:
        return get_config().get_bool(self.meta.enabled_key)

    def validate(self) -> IntegrationStatus:
        if not self.is_enabled():
            return IntegrationStatus(False, "Prometheus ingest is disabled")
        return IntegrationStatus(True, "Webhook ingest ready at POST /hook")

    def handle_webhook(self, payload: dict[str, Any], ingest_fn) -> tuple[int, bytes]:
        """Delegate Alertmanager payload to core ingest callback."""
        import json

        if not self.is_enabled():
            return 503, b'{"ok":false,"error":"prometheus integration disabled"}'
        if not isinstance(payload, dict):
            return 400, b'{"ok":false,"error":"expected JSON object"}'
        events = ingest_fn(payload)
        if not events:
            return 200, b'{"ok":true,"skipped":"ignored or empty alerts"}'
        return 200, json.dumps({"ok": True, "incidents": len(events)}).encode("utf-8")
