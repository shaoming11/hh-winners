"""JSON-lines codec used at the Mega serial boundary and in simulator checks."""
from __future__ import annotations

import json
from typing import Any


def encode_line(message: dict[str, Any]) -> str:
    if not isinstance(message, dict):
        raise TypeError("JSON-line messages must be objects")
    return json.dumps(message, separators=(",", ":"), allow_nan=False) + "\n"


def decode_line(line: str | bytes) -> dict[str, Any]:
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("Expected one JSON object per line")
    return value


class LineDecoder:
    """Collect partial serial reads and return every complete JSON object."""

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, data: str | bytes) -> list[dict[str, Any]]:
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        self._buffer += data
        messages = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                messages.append(decode_line(line))
        return messages
