"""Receiving uploaded files — multipart, with the standard library.

`cgi.FieldStorage` was removed in Python 3.13, so `email.parser` is used
instead: multipart/form-data is a MIME message underneath.
"""

from __future__ import annotations

from email.parser import BytesParser
from email.policy import default

MAX_BYTES = 8 * 1024 * 1024        # 8MB — every CV is far smaller


class TooBig(RuntimeError):
    pass


def parse(content_type: str, body: bytes) -> dict[str, tuple[str, bytes]]:
    """Returns {field name: (filename, content)}. A plain text field has an
    empty filename."""
    if len(body) > MAX_BYTES:
        raise TooBig(f"File too large (limit {MAX_BYTES // 1024 // 1024}MB)")

    head = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
    message = BytesParser(policy=default).parsebytes(head + body)
    out: dict[str, tuple[str, bytes]] = {}
    if not message.is_multipart():
        return out
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        payload = part.get_payload(decode=True) or b""
        out[str(name)] = (part.get_filename() or "", payload)
    return out
