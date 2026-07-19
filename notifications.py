"""Incident-centric notifications via the ntfy integration."""

from __future__ import annotations

from typing import Any

from config import ConfigStore, get_config
from integrations.registry import get_registry


class NotificationService:
    def __init__(self, store: Any, config: ConfigStore | None = None) -> None:
        self.store = store
        self._config = config

    @property
    def config(self) -> ConfigStore:
        return self._config or get_config()

    def settings(self) -> dict[str, Any]:
        return self.config.ntfy_settings()

    def save_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        if "enabled" in settings:
            updates["ntfy.enabled"] = bool(settings["enabled"])
        if "topic" in settings and str(settings["topic"]).strip():
            updates["ntfy.topic"] = str(settings["topic"]).strip()
        if "show_noise" in settings:
            updates["display.show_noise"] = bool(settings["show_noise"])
        if isinstance(settings.get("events"), dict):
            for key, value in settings["events"].items():
                updates[f"ntfy.events.{key}"] = bool(value)
        self.config.save_ui(updates)
        return self.settings()

    def should_notify(self, event: str) -> bool:
        return get_registry().ntfy().should_notify(event)

    def notify(self, incident_id: str, event: str) -> tuple[int, bytes] | None:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            return None
        return get_registry().ntfy().notify(incident, event)

    def notify_many(self, items: list[tuple[str, str]]) -> None:
        """Dedupe by incident id; highest-priority event wins per incident."""
        priority = {
            "resolved": 0,
            "reopened": 1,
            "created": 2,
            "manual": 2,
            "merged": 3,
            "acknowledged": 4,
            "updated": 5,
        }
        chosen: dict[str, str] = {}
        for incident_id, event in items:
            current = chosen.get(incident_id)
            if current is None or priority.get(event, 99) < priority.get(current, 99):
                chosen[incident_id] = event
        for incident_id, event in chosen.items():
            self.notify(incident_id, event)
