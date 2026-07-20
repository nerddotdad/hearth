"""Minimal Ollama HTTP helpers for AIOps model discovery."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(Exception):
    def __init__(self, message: str, *, detail: Any = None):
        super().__init__(message)
        self.detail = detail


def list_models(base_url: str, *, timeout: float = 10.0) -> list[str]:
    """Return installed model names from Ollama GET /api/tags."""
    root = (base_url or "").strip().rstrip("/")
    if not root:
        raise OllamaError("Ollama URL is not set")
    url = f"{root}/api/tags"
    req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"Ollama returned HTTP {exc.code}", detail=body) from exc
    except urllib.error.URLError as exc:
        raise OllamaError(f"Ollama unreachable: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise OllamaError("Ollama returned invalid JSON") from exc

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        return []
    names: list[str] = []
    for item in models:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return sorted(set(names), key=str.lower)
