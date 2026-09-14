"""A minimal WebSocket client — just enough to talk to the Chrome DevTools
Protocol.

The Python standard library has no WebSocket client. But the part of the
protocol needed here is simple: an HTTP handshake, then masked text frames.

NOT a complete WebSocket client. No compression, no fragmentation on send.
Enough for CDP, and CDP is the only thing it is used for.
"""

from __future__ import annotations

import base64
import os
import socket
import struct
from urllib.parse import urlparse

TEXT, CLOSE, PING, PONG = 0x1, 0x8, 0x9, 0xA


class WSError(RuntimeError):
    pass


class WebSocket:
    def __init__(self, url: str, timeout: float = 30.0):
        parts = urlparse(url)
        self.sock = socket.create_connection(
            (parts.hostname, parts.port or 80), timeout=timeout)
        self.sock.settimeout(timeout)
        # _buf must be declared BEFORE the handshake: the 101 response and
        # the first data frame can arrive in one TCP read, and _handshake
        # keeps the remainder in _buf. Assigning b"" AFTER the handshake
        # throws exactly that remainder away.
        self._buf = b""
        self._handshake(parts.path or "/", parts.hostname, parts.port)

    # --- the handshake -----------------------------------------------------
    def _handshake(self, path: str, host: str, port: int | None) -> None:
        key = base64.b64encode(os.urandom(16)).decode()
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(request.encode())

        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise WSError("Chrome closed the connection mid-handshake")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise WSError(f"handshake failed: {head.split(chr(13).encode())[0][:80]!r}")
        self._buf = head.split(b"\r\n\r\n", 1)[1]

    # --- sending -----------------------------------------------------------
    def send(self, text: str) -> None:
        payload = text.encode()
        header = bytearray([0x80 | TEXT])
        length = len(payload)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", length)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", length)
        mask = os.urandom(4)                       # a client MUST mask
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    # --- receiving ---------------------------------------------------------
    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise WSError("Chrome closed the connection")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self) -> str:
        """Return one text message. Reassembles fragments itself."""
        parts: list[bytes] = []
        while True:
            first, second = self._read(2)
            fin, opcode = first & 0x80, first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read(8))[0]
            mask = self._read(4) if second & 0x80 else None
            data = self._read(length) if length else b""
            if mask:
                data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

            if opcode == CLOSE:
                raise WSError("Chrome sent a close frame")
            if opcode == PING:
                self.sock.sendall(bytes([0x80 | PONG, 0x80 | len(data)])
                                  + b"\x00\x00\x00\x00" + data)
                continue
            if opcode == PONG:
                continue
            parts.append(data)
            if fin:
                return b"".join(parts).decode("utf-8", "replace")

    def close(self) -> None:
        try:
            self.sock.sendall(bytes([0x80 | CLOSE, 0x80]) + b"\x00\x00\x00\x00")
        except OSError:
            pass
        finally:
            self.sock.close()
