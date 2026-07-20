"""Lightweight audit log for sandbox tool use (in-process + optional event)."""

from __future__ import annotations

import logging
from typing import Any

LOG = logging.getLogger("hearth.sandbox.audit")


def log_exec(
    *,
    incident_id: str,
    actor: str,
    command: str,
    exit_code: int | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    LOG.info(
        "sandbox_exec incident=%s actor=%s exit=%s cmd=%s detail=%s",
        incident_id,
        actor,
        exit_code,
        command[:200],
        detail or {},
    )
