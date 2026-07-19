"""Publish incidents to ntfy — notifications always flow incident → ntfy."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from message_format import incident_ntfy_body, incident_ntfy_priority, incident_ntfy_tags, incident_ntfy_title


def _http_header(value: str) -> str:
    """urllib requires ISO-8859-1 header values (e.g. ntfy X-Title)."""
    return value.encode("latin-1", errors="replace").decode("latin-1")


def _headers_for_incident(
    incident: dict[str, Any],
    *,
    event: str,
    topic: str,
    public_url: str,
    incidents_public_base_url: str,
) -> dict[str, str]:
    incident_id = str(incident.get("id") or "").strip()
    public_url = public_url.rstrip("/")
    incidents_base = incidents_public_base_url.rstrip("/")

    click_url = f"{public_url}/{topic}" if public_url else ""
    if incidents_base and incident_id:
        click_url = f"{incidents_base}/incidents/{incident_id}"

    headers = {
        "Content-Type": "text/plain; charset=utf-8",
        "X-Title": _http_header(incident_ntfy_title(incident, event=event)),
        "X-Priority": _http_header(incident_ntfy_priority(incident, event=event)),
        "Markdown": "yes",
    }
    if click_url:
        headers["X-Click"] = _http_header(click_url)

    tags = incident_ntfy_tags(incident, event=event)
    if tags:
        headers["X-Tags"] = _http_header(tags)

    if incident_id:
        headers["X-Sequence-ID"] = incident_id

    actions: list[str] = []
    if incidents_base and incident_id:
        view = f"{incidents_base}/incidents/{incident_id}"
        actions.append(f"view, Open incident, {view}, clear=true")
        investigate = f"{incidents_base}/incidents/{incident_id}/investigate"
        actions.append(f"view, Investigate, {investigate}, clear=true")
    if actions:
        headers["X-Actions"] = _http_header("; ".join(actions))

    return headers


def publish_incident(
    incident: dict[str, Any],
    *,
    event: str = "updated",
    topic: str | None = None,
    base_url: str | None = None,
    public_url: str | None = None,
    incidents_public_base_url: str | None = None,
) -> tuple[int, bytes]:
    """POST one incident notification to ntfy."""
    from config import config_or_none

    cfg = config_or_none()
    resolved_base = (base_url if base_url is not None else (cfg.get_str("ntfy.base_url") if cfg else "")).rstrip("/")
    resolved_topic = topic or (cfg.get_str("ntfy.topic") if cfg else "") or "homelab-alerts"
    resolved_public = public_url if public_url is not None else (cfg.get_str("ntfy.public_url") if cfg else "")
    resolved_incidents = (
        incidents_public_base_url
        if incidents_public_base_url is not None
        else (cfg.get_str("core.incidents_public_base_url") if cfg else "")
    )
    if not resolved_base:
        raise ValueError("ntfy base URL is not configured")

    body = incident_ntfy_body(incident, event=event).encode("utf-8")
    req = urllib.request.Request(
        f"{resolved_base}/{resolved_topic}",
        data=body,
        method="POST",
        headers=_headers_for_incident(
            incident,
            event=event,
            topic=resolved_topic,
            public_url=str(resolved_public or ""),
            incidents_public_base_url=str(resolved_incidents or ""),
        ),
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
