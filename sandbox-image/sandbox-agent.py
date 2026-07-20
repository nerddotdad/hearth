#!/usr/bin/env python3
"""Lightweight triage agent inside hearth-sandbox pods.

HTTP:
  GET  /health
  POST /exec   {"command":"kubectl get pods -A","timeout":120} → stdout/stderr/exit_code

WebSocket:
  GET  /terminal  (upgrade) — interactive PTY shell
"""

from __future__ import annotations

import json
import os
import pty
import select
import struct
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

PORT = int(os.environ.get("SANDBOX_AGENT_PORT", "8080"))
DEFAULT_SHELL = os.environ.get("SANDBOX_SHELL", "/bin/bash")
MAX_BODY = 256 * 1024
MAX_OUTPUT = 2 * 1024 * 1024


def _ws_accept(key: str) -> str:
    import base64
    import hashlib

    guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
    return base64.b64encode(hashlib.sha1((key + guid).encode()).digest()).decode()


def _ws_encode(payload: bytes, opcode: int = 0x1) -> bytes:
    header = bytearray([0x80 | (opcode & 0x0F)])
    n = len(payload)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(127)
        header.extend(struct.pack("!Q", n))
    return bytes(header) + payload


def _ws_read(rfile) -> tuple[int, bytes]:
    header = rfile.read(2)
    if len(header) < 2:
        raise ConnectionError("closed")
    opcode = header[0] & 0x0F
    masked = bool(header[1] & 0x80)
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", rfile.read(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", rfile.read(8))[0]
    mask = rfile.read(4) if masked else b""
    payload = rfile.read(length) if length else b""
    if masked:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    return opcode, payload


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _json(self, code: int, body: dict[str, Any]) -> None:
        raw = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/health":
            self._json(200, {"ok": True, "service": "hearth-sandbox-agent"})
            return
        if path == "/terminal":
            self._terminal()
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/exec":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            self._json(413, {"error": "body too large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"error": "invalid json"})
            return
        command = str(payload.get("command") or "").strip()
        if not command:
            self._json(400, {"error": "command required"})
            return
        try:
            timeout = float(payload.get("timeout") or 120)
        except (TypeError, ValueError):
            timeout = 120.0
        timeout = max(1.0, min(timeout, 600.0))
        try:
            proc = subprocess.run(
                ["/bin/bash", "-lc", command],
                capture_output=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
            stdout = proc.stdout[:MAX_OUTPUT].decode("utf-8", errors="replace")
            stderr = proc.stderr[:MAX_OUTPUT].decode("utf-8", errors="replace")
            self._json(
                200,
                {
                    "ok": True,
                    "exit_code": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )
        except subprocess.TimeoutExpired:
            self._json(504, {"error": "command timed out", "timeout": timeout})
        except OSError as exc:
            self._json(500, {"error": str(exc)})

    def _terminal(self) -> None:
        key = self.headers.get("Sec-WebSocket-Key")
        if not key or self.headers.get("Upgrade", "").lower() != "websocket":
            self._json(400, {"error": "websocket upgrade required"})
            return
        self.send_response(101)
        self.send_header("Upgrade", "websocket")
        self.send_header("Connection", "Upgrade")
        self.send_header("Sec-WebSocket-Accept", _ws_accept(key))
        self.end_headers()

        master, slave = pty.openpty()
        shell = DEFAULT_SHELL if os.path.isfile(DEFAULT_SHELL) else "/bin/sh"
        proc = subprocess.Popen(
            [shell, "-l"],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            env=os.environ.copy(),
            close_fds=True,
            preexec_fn=os.setsid,
        )
        os.close(slave)
        stop = threading.Event()

        def pump_out() -> None:
            try:
                while not stop.is_set() and proc.poll() is None:
                    r, _, _ = select.select([master], [], [], 0.5)
                    if not r:
                        continue
                    data = os.read(master, 4096)
                    if not data:
                        break
                    self.wfile.write(_ws_encode(data, opcode=0x2))
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                stop.set()

        t = threading.Thread(target=pump_out, daemon=True)
        t.start()
        try:
            while not stop.is_set() and proc.poll() is None:
                opcode, payload = _ws_read(self.rfile)
                if opcode in (0x8,):  # close
                    break
                if opcode in (0x9,):  # ping
                    self.wfile.write(_ws_encode(payload, opcode=0xA))
                    self.wfile.flush()
                    continue
                if opcode in (0x1, 0x2) and payload:
                    os.write(master, payload)
        except Exception:
            pass
        finally:
            stop.set()
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                os.close(master)
            except Exception:
                pass


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"hearth-sandbox-agent listening on :{PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
