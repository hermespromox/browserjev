from __future__ import annotations

from typing import Any

from .http import TransportError


class CascadeTransport:
    def __init__(self, transports: list[Any]):
        if not transports:
            raise ValueError("at least one transport is required")
        self.transports = transports
        self.name = "cascade"

    async def fetch(self, url: str):
        last_error: TransportError | None = None
        for transport in self.transports:
            try:
                return await transport.fetch(url)
            except TransportError as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        raise TransportError("no transport could fetch the URL")
