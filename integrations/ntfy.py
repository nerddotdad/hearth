"""ntfy notification integration."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from typing import Any

from config import get_config
from integrations.base import IntegrationMeta, IntegrationStatus
from ntfy_publish import publish_incident


class NtfyIntegration:
    meta = IntegrationMeta(
        id="ntfy",
        name="ntfy",
        kind="notify",
        description="Push incident notifications to an ntfy topic.",
        config_group="ntfy",
        enabled_key="ntfy.enabled",
        field_keys=[
            "ntfy.enabled",
            "ntfy.base_url",
            "ntfy.topic",
            "ntfy.public_url",
            "ntfy.events.created",
            "ntfy.events.updated",
            "ntfy.events.resolved",
            "ntfy.events.reopened",
            "ntfy.events.manual",
            "ntfy.events.acknowledged",
            "ntfy.events.merged",
        ],
    )

    def is_enabled(self) -> bool:
        return get_config().get_bool(self.meta.enabled_key)

    def validate(self) -> IntegrationStatus:
        cfg = get_config()
        if not self.is_enabled():
            return IntegrationStatus(False, "ntfy integration is disabled")
        base = cfg.get_str("ntfy.base_url")
        if not base:
            return IntegrationStatus(False, "ntfy base URL is not configured")
        topic = cfg.get_str("ntfy.topic") or "homelab-alerts"
        url = f"{base.rstrip('/')}/{topic}"
        req = urllib.request.Request(url, data=b"", method="POST", headers={"X-Title": "Hearth test"})
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return IntegrationStatus(True, f"Connected ({resp.status}) — test message posted to {topic}")
        except urllib.error.HTTPError as exc:
            # ntfy may reject empty body; 4xx with reachable server still counts as reachable
            if exc.code < 500:
                return IntegrationStatus(True, f"Reachable at {base} (HTTP {exc.code})")
            return IntegrationStatus(False, f"ntfy HTTP {exc.code}", detail=exc.read()[:200])
        except urllib.error.URLError as exc:
            return IntegrationStatus(False, f"ntfy unreachable: {exc.reason}")
        except Exception as exc:
            return IntegrationStatus(False, str(exc))

    def should_notify(self, event: str) -> bool:
        cfg = get_config()
        if not self.is_enabled():
            return False
        if not cfg.get_str("ntfy.base_url"):
            return False
        return bool(cfg.get(f"ntfy.events.{event}"))

    def notify(self, incident: dict[str, Any], event: str) -> tuple[int, bytes] | None:
        if not self.should_notify(event):
            return None
        if incident.get("status") == "merged":
            return None
        cfg = get_config()
        topic = cfg.get_str("ntfy.topic") or "homelab-alerts"
        try:
            status, body = publish_incident(
                incident,
                event=event,
                topic=topic,
                base_url=cfg.get_str("ntfy.base_url"),
                public_url=cfg.get_str("ntfy.public_url"),
                incidents_public_base_url=cfg.get_str("core.incidents_public_base_url"),
            )
            if status >= 400:
                sys.stderr.write(
                    f"ntfy incident notify failed ({status}) incident={incident.get('id')} event={event}\n"
                )
            else:
                sys.stderr.write(
                    f"ntfy notified incident={incident.get('id')} event={event} topic={topic}\n"
                )
            return status, body
        except Exception as exc:
            sys.stderr.write(f"ntfy notify error incident={incident.get('id')}: {exc}\n")
            return None
