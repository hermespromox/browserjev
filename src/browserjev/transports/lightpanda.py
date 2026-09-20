from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import websockets

from ..dom import parse_page
from ..models import PageSnapshot
from .http import TransportError


class CDPError(TransportError):
    pass


class LightpandaCDPRenderer:
    def __init__(self, endpoint: str | None = None, *, timeout: float = 20.0):
        self.endpoint: str = (
            endpoint or os.getenv("LIGHTPANDA_CDP_URL") or "ws://127.0.0.1:9222"
        )
        self.timeout = timeout
        self._request_id = 0

    async def _call(
        self,
        websocket: Any,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self._request_id += 1
        request_id = self._request_id
        message: dict[str, Any] = {"id": request_id, "method": method, "params": params or {}}
        if session_id:
            message["sessionId"] = session_id
        await websocket.send(json.dumps(message))
        while True:
            response = json.loads(await asyncio.wait_for(websocket.recv(), self.timeout))
            if response.get("id") != request_id:
                continue
            if "error" in response:
                raise CDPError(f"CDP {method} failed: {response['error']}")
            return response.get("result", {})

    async def render(self, url: str) -> tuple[str, str]:
        try:
            async with websockets.connect(self.endpoint, open_timeout=self.timeout) as websocket:
                target = await self._call(
                    websocket, "Target.createTarget", {"url": "about:blank"}
                )
                attached = await self._call(
                    websocket,
                    "Target.attachToTarget",
                    {"targetId": target["targetId"], "flatten": True},
                )
                session_id = attached["sessionId"]
                await self._call(websocket, "Page.enable", session_id=session_id)
                await self._call(
                    websocket, "Page.navigate", {"url": url}, session_id=session_id
                )
                for _ in range(100):
                    ready = await self._call(
                        websocket,
                        "Runtime.evaluate",
                        {"expression": "document.readyState", "returnByValue": True},
                        session_id=session_id,
                    )
                    value = ready.get("result", {}).get("value")
                    if value in {"interactive", "complete"}:
                        break
                    await asyncio.sleep(0.05)
                expression = (
                    "JSON.stringify({url:location.href,"
                    "html:document.documentElement.outerHTML})"
                )
                rendered = await self._call(
                    websocket,
                    "Runtime.evaluate",
                    {"expression": expression, "returnByValue": True},
                    session_id=session_id,
                )
                value = rendered.get("result", {}).get("value")
                data = json.loads(value)
                return data["url"], data["html"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError, TimeoutError) as exc:
            raise CDPError(f"Lightpanda CDP render failed: {exc}") from exc


class LightpandaTransport:
    name = "lightpanda"

    def __init__(
        self,
        *,
        renderer: Any | None = None,
        max_text: int = 20_000,
        max_links: int = 40,
    ):
        self.renderer = renderer or LightpandaCDPRenderer()
        self.max_text = max_text
        self.max_links = max_links

    async def fetch(self, url: str) -> PageSnapshot:
        final_url, html = await self.renderer.render(url)
        page = parse_page(
            final_url,
            html,
            max_text=self.max_text,
            max_links=self.max_links,
        )
        page.transport = self.name
        return page
