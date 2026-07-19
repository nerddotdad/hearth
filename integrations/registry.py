"""Discover and resolve Hearth integrations."""

from __future__ import annotations

from typing import Iterable

from integrations.base import Integration, IntegrationMeta, IntegrationStatus
from integrations.hermes import HermesIntegration
from integrations.ntfy import NtfyIntegration
from integrations.prometheus import PrometheusIntegration


class IntegrationRegistry:
    def __init__(self, integrations: Iterable[Integration] | None = None) -> None:
        items = list(integrations) if integrations is not None else [
            PrometheusIntegration(),
            NtfyIntegration(),
            HermesIntegration(),
        ]
        self._by_id: dict[str, Integration] = {i.meta.id: i for i in items}

    def all(self) -> list[Integration]:
        return list(self._by_id.values())

    def get(self, integration_id: str) -> Integration | None:
        return self._by_id.get(integration_id)

    def require(self, integration_id: str) -> Integration:
        integ = self.get(integration_id)
        if integ is None:
            raise KeyError(f"unknown integration: {integration_id}")
        return integ

    def prometheus(self) -> PrometheusIntegration:
        return self.require("prometheus")  # type: ignore[return-value]

    def ntfy(self) -> NtfyIntegration:
        return self.require("ntfy")  # type: ignore[return-value]

    def hermes(self) -> HermesIntegration:
        return self.require("hermes")  # type: ignore[return-value]

    def metas(self) -> list[IntegrationMeta]:
        return [i.meta for i in self.all()]

    def validate(self, integration_id: str) -> IntegrationStatus:
        integ = self.require(integration_id)
        return integ.validate()

    def status_summary(self, *, probe: bool = False) -> list[dict]:
        """Lightweight enabled/kind listing. Set probe=True to run Test connection checks."""
        rows = []
        for integ in self.all():
            row = {
                "id": integ.meta.id,
                "name": integ.meta.name,
                "kind": integ.meta.kind,
                "enabled": integ.is_enabled(),
            }
            if probe:
                st = integ.validate()
                row["ok"] = st.ok
                row["message"] = st.message
            rows.append(row)
        return rows


_REGISTRY: IntegrationRegistry | None = None


def init_registry(registry: IntegrationRegistry | None = None) -> IntegrationRegistry:
    global _REGISTRY
    _REGISTRY = registry or IntegrationRegistry()
    return _REGISTRY


def get_registry() -> IntegrationRegistry:
    if _REGISTRY is None:
        raise RuntimeError("IntegrationRegistry not initialized")
    return _REGISTRY
