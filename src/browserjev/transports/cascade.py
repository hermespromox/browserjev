from __future__ import annotations

from typing import Any

from .http import JavaScriptRequired, TransportError


class CascadeTransport:
    def __init__(self, transports: list[Any]):
        if not transports:
            raise ValueError("at least one transport is required")
        self.transports = transports
        self.name = "cascade"

    async def fetch(self, url: str):
        fallback_reason: JavaScriptRequired | None = None
        try:
            return await self.transports[0].fetch(url)
        except JavaScriptRequired as exc:
            if len(self.transports) == 1:
                raise
            fallback_reason = exc

        assert fallback_reason is not None
        last_error: TransportError = fallback_reason
        for transport in self.transports[1:]:
            try:
                return await transport.fetch(url)
            except TransportError as exc:
                last_error = exc
        raise last_error from fallback_reason
