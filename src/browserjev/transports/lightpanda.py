from __future__ import annotations

import asyncio
import json
import os
from typing import Any

import websockets

from ..dom import parse_page
from ..models import PageSnapshot
from ..security import Resolver, default_resolver, validate_public_url
from .http import TransportError


class CDPError(TransportError):
    pass


def _truncation_expression(max_html: int) -> str:
    """Ask the page for its markup, already sliced to the transport budget.

    Slicing inside the browser keeps the CDP payload bounded: a hostile or
    simply enormous document never crosses the WebSocket in full. The
    renderer still re-checks the received length, so a page that ignores or
    forges the returned ``truncated`` flag cannot bypass the budget.
    """
    return (
        "(() => {"
        "  const html = document.documentElement ? document.documentElement.outerHTML : '';"
        f"  const cap = {max_html};"
        "  return JSON.stringify({"
        "    url: location.href,"
        "    html: html.slice(0, cap),"
        "    truncated: html.length > cap"
        "  });"
        "})()"
    )


class LightpandaCDPRenderer:
    def __init__(
        self,
        endpoint: str | None = None,
        *,
        timeout: float = 20.0,
        max_html: int = 2_000_000,
    ):
        self.endpoint: str = endpoint or os.getenv("LIGHTPANDA_CDP_URL") or "ws://127.0.0.1:9222"
        self.timeout = timeout
        self.max_html = max_html
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

    async def render(self, url: str) -> tuple[str, str, bool]:
        try:
            async with websockets.connect(self.endpoint, open_timeout=self.timeout) as websocket:
                target = await self._call(websocket, "Target.createTarget", {"url": "about:blank"})
                attached = await self._call(
                    websocket,
                    "Target.attachToTarget",
                    {"targetId": target["targetId"], "flatten": True},
                )
                session_id = attached["sessionId"]
                await self._call(websocket, "Page.enable", session_id=session_id)
                await self._call(websocket, "Page.navigate", {"url": url}, session_id=session_id)
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
                rendered = await self._call(
                    websocket,
                    "Runtime.evaluate",
                    {
                        "expression": _truncation_expression(self.max_html),
                        "returnByValue": True,
                    },
                    session_id=session_id,
                )
                value = rendered.get("result", {}).get("value")
                data = json.loads(value)
                html = data["html"]
                truncated = bool(data.get("truncated"))
                if len(html) > self.max_html:
                    html = html[: self.max_html]
                    truncated = True
                return data["url"], html, truncated
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
        max_html: int = 2_000_000,
        allow_private_networks: bool = False,
        resolver: Resolver = default_resolver,
    ):
        self.renderer = renderer or LightpandaCDPRenderer(max_html=max_html)
        self.max_text = max_text
        self.max_links = max_links
        self.max_html = max_html
        self.allow_private_networks = allow_private_networks
        self.resolver = resolver

    @staticmethod
    def _unpack(rendered: Any) -> tuple[str, str, bool]:
        """Accept both the 2-tuple and the 3-tuple renderer contract."""
        if hasattr(rendered, "__len__") and not isinstance(rendered, str):
            values = list(rendered)
            if len(values) == 3:
                return str(values[0]), str(values[1]), bool(values[2])
            if len(values) == 2:
                return str(values[0]), str(values[1]), False
        raise TransportError("renderer must return (url, html) or (url, html, truncated)")

    async def fetch(self, url: str) -> PageSnapshot:
        start_url = await validate_public_url(
            url,
            allow_private_networks=self.allow_private_networks,
            resolver=self.resolver,
        )
        final_url, html, truncated = self._unpack(await self.renderer.render(start_url))
        if len(html) > self.max_html:
            html = html[: self.max_html]
            truncated = True
        # The browser may have been redirected (meta refresh, JS navigation),
        # so the landing URL is re-validated against the same SSRF policy.
        # An UnsafeURLError here is deliberately not downgraded to a
        # TransportError: the cascade must never treat a security rejection
        # as a recoverable transport failure.
        landing = await validate_public_url(
            final_url,
            allow_private_networks=self.allow_private_networks,
            resolver=self.resolver,
        )

        page = parse_page(
            landing,
            html,
            max_text=self.max_text,
            max_links=self.max_links,
        )
        page.transport = self.name
        page.truncated = truncated
        return page
