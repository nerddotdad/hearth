"""HTTP client for hearth-agent (Hermes Agent OpenAI-compatible API)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Iterator


class AgentError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None, detail: Any = None) -> None:
        super().__init__(message)
        self.status = status
        self.detail = detail


class HearthAgentClient:
    """Talk to Hermes Agent core via /v1/chat/completions and /v1/responses."""

    def __init__(self, *, base_url: str, api_key: str, model: str = "hermes-agent") -> None:
        self.base = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model or "hermes-agent"
        if not self.base:
            raise AgentError("Hearth Agent URL is not configured")
        if not self.api_key:
            raise AgentError("Hearth Agent API key is not configured")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def health(self) -> dict[str, Any]:
        url = f"{self.base}/health"
        req = urllib.request.Request(url, method="GET", headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {"ok": True}
        except urllib.error.HTTPError as exc:
            # Some builds expose /v1/models instead
            if exc.code == 404:
                return self.list_models()
            raise AgentError("hearth-agent health failed", status=exc.code) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"hearth-agent unreachable: {exc.reason}") from exc
        except json.JSONDecodeError:
            return {"ok": True}

    def list_models(self) -> dict[str, Any]:
        url = f"{self.base}/v1/models"
        req = urllib.request.Request(url, method="GET", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AgentError("hearth-agent /v1/models failed", status=exc.code, detail=body[:500]) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"hearth-agent unreachable: {exc.reason}") from exc

    def chat_completions(
        self,
        messages: list[dict[str, str]],
        *,
        stream: bool = False,
        timeout: int = 600,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/v1/chat/completions",
            data=data,
            method="POST",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AgentError("chat/completions failed", status=exc.code, detail=body[:800]) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"hearth-agent unreachable: {exc.reason}") from exc

    def responses(
        self,
        *,
        input_text: str,
        conversation: str,
        instructions: str | None = None,
        timeout: int = 600,
    ) -> dict[str, Any]:
        """OpenAI Responses API with named conversation (server-side history)."""
        payload: dict[str, Any] = {
            "model": self.model,
            "input": input_text,
            "conversation": conversation,
            "store": True,
        }
        if instructions:
            payload["instructions"] = instructions
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/v1/responses",
            data=data,
            method="POST",
            headers=self._headers(),
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            # Fall back to chat completions if responses not available
            if exc.code in (404, 405):
                return self.chat_completions(
                    [
                        *([{"role": "system", "content": instructions}] if instructions else []),
                        {"role": "user", "content": input_text},
                    ],
                    timeout=timeout,
                )
            raise AgentError("responses failed", status=exc.code, detail=body[:800]) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"hearth-agent unreachable: {exc.reason}") from exc

    @staticmethod
    def extract_assistant_text(result: dict[str, Any]) -> str:
        # chat.completion shape
        choices = result.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict) and msg.get("content"):
                return str(msg["content"])
        # responses shape
        output = result.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "message":
                    content = item.get("content") or []
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") in ("output_text", "text"):
                                parts.append(str(part.get("text") or ""))
                    elif isinstance(content, str):
                        parts.append(content)
            if parts:
                return "\n".join(p for p in parts if p)
        if result.get("output_text"):
            return str(result["output_text"])
        return json.dumps(result)[:4000]

    def iter_chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        timeout: int = 600,
    ) -> Iterator[str]:
        """Yield text deltas from a streaming chat completion."""
        payload = {"model": self.model, "messages": messages, "stream": True}
        data = json.dumps(payload).encode("utf-8")
        headers = self._headers()
        headers["Accept"] = "text/event-stream"
        req = urllib.request.Request(
            f"{self.base}/v1/chat/completions",
            data=data,
            method="POST",
            headers=headers,
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AgentError("stream failed", status=exc.code, detail=body[:500]) from exc
        except urllib.error.URLError as exc:
            raise AgentError(f"hearth-agent unreachable: {exc.reason}") from exc
        try:
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text or text.startswith(":"):
                    continue
                if text.startswith("data:"):
                    data_s = text[5:].strip()
                    if data_s == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_s)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if choices and isinstance(choices[0], dict):
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield str(content)
        finally:
            resp.close()
