"""Compatibility shim — notification settings now live in config.ConfigStore."""

from __future__ import annotations

from typing import Any

from config import get_config


def default_settings() -> dict[str, Any]:
    return get_config().ntfy_settings()


class SettingsStore:
    """Deprecated wrapper kept for import compatibility; prefer ConfigStore."""

    def __init__(self, path=None) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        return get_config().ntfy_settings()

    def save(self, settings: dict[str, Any]) -> dict[str, Any]:
        cfg = get_config()
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
        cfg.save_ui(updates)
        return cfg.ntfy_settings()
