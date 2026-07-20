"""Minimal RFC6455 WebSocket helpers for BaseHTTPRequestHandler."""

from __future__ import annotations

import base64
import hashlib
import struct
from typing import BinaryIO


GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def accept_key(sec_websocket_key: str) -> str:
    digest = hashlib.sha1((sec_websocket_key + GUID).encode("utf-8")).digest()
    return base64.b64encode(digest).decode("ascii")


def encode_frame(payload: bytes, *, opcode: int = 0x1, mask: bool = False) -> bytes:
    fin_opcode = 0x80 | (opcode & 0x0F)
    length = len(payload)
    header = bytearray([fin_opcode])
    if length < 126:
        header.append((0x80 if mask else 0x00) | length)
    elif length < 65536:
        header.append((0x80 if mask else 0x00) | 126)
        header.extend(struct.pack("!H", length))
    else:
        header.append((0x80 if mask else 0x00) | 127)
        header.extend(struct.pack("!Q", length))
    if mask:
        import os

        masking_key = os.urandom(4)
        header.extend(masking_key)
        payload = bytes(b ^ masking_key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + payload


def read_frame(rfile: BinaryIO) -> tuple[int, bytes]:
    header = rfile.read(2)
    if len(header) < 2:
        raise ConnectionError("websocket closed")
    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        raw = rfile.read(2)
        length = struct.unpack("!H", raw)[0]
    elif length == 127:
        raw = rfile.read(8)
        length = struct.unpack("!Q", raw)[0]
    masking_key = rfile.read(4) if masked else b""
    payload = rfile.read(length) if length else b""
    if masked:
        payload = bytes(b ^ masking_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload
