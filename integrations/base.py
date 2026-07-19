"""Integration protocol and shared types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

IntegrationKind = Literal["ingest", "notify", "investigate"]


@dataclass
class IntegrationStatus:
    ok: bool
    message: str
    detail: Any = None


@dataclass
class IntegrationMeta:
    id: str
    name: str
    kind: IntegrationKind
    description: str
    config_group: str
    enabled_key: str
    field_keys: list[str] = field(default_factory=list)


class Integration(Protocol):
    meta: IntegrationMeta

    def is_enabled(self) -> bool: ...

    def validate(self) -> IntegrationStatus: ...
