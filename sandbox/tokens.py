"""Incident-scoped sandbox attach tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any


def issue_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_matches(token: str, token_hash: str) -> bool:
    if not token or not token_hash:
        return False
    return hmac.compare_digest(hash_token(token), token_hash)


def sandbox_record_from_enrichment(enrichment: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(enrichment, dict):
        return {}
    raw = enrichment.get("sandbox")
    return dict(raw) if isinstance(raw, dict) else {}
