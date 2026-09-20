from __future__ import annotations

import httpx

from ..dom import parse_page
from ..models import PageSnapshot


class TransportError(RuntimeError):
    pass


class JavaScriptRequired(TransportError):
    pass


class HTTPTransport:
    name = "httpx"

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
        min_text: int = 40,
        max_text: int = 20_000,
        max_links: int = 40,
    ):
        self._client = client
        self.timeout = timeout
        self.min_text = min_text
        self.max_text = max_text
        self.max_links = max_links

    async def fetch(self, url: str) -> PageSnapshot:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
            headers={"User-Agent": "BrowserJev/0.1 (+https://github.com/hermespromox/browserjev)"},
        )
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "BrowserJev/0.1 (+https://github.com/hermespromox/browserjev)"
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TransportError(str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()

        page = parse_page(
            str(response.url),
            response.text,
            max_text=self.max_text,
            max_links=self.max_links,
        )
        page.transport = self.name
        if len(page.text) < self.min_text and "<script" in response.text.lower():
            message = f"static response has only {len(page.text)} visible characters"
            raise JavaScriptRequired(message)
        return page
