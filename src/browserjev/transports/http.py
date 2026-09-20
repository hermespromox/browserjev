from __future__ import annotations

import ipaddress
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from ..dom import parse_page
from ..models import PageSnapshot
from ..security import Resolver, UnsafeURLError, default_resolver, normalize_start_url, resolve_url


class TransportError(RuntimeError):
    pass


class JavaScriptRequired(TransportError):
    pass


class ResponseTooLarge(TransportError):
    pass


class UnsupportedContentType(TransportError):
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
        max_response_bytes: int = 2_000_000,
        max_redirects: int = 10,
        allow_private_networks: bool = False,
        resolver: Resolver = default_resolver,
    ):
        self._client = client
        self.timeout = timeout
        self.min_text = min_text
        self.max_text = max_text
        self.max_links = max_links
        self.max_response_bytes = max_response_bytes
        self.max_redirects = max_redirects
        self.allow_private_networks = allow_private_networks
        self.resolver = resolver

    @staticmethod
    def _connection_url(logical_url: str, address: str) -> tuple[str, str, str]:
        parsed = urlsplit(logical_url)
        hostname = parsed.hostname
        assert hostname is not None
        ip = ipaddress.ip_address(address)
        connect_host = f"[{ip}]" if ip.version == 6 else str(ip)
        connect_netloc = connect_host if parsed.port is None else f"{connect_host}:{parsed.port}"
        connect_url = urlunsplit((parsed.scheme, connect_netloc, parsed.path, parsed.query, ""))
        default_port = 443 if parsed.scheme == "https" else 80
        host_header = (
            hostname if parsed.port in {None, default_port} else f"{hostname}:{parsed.port}"
        )
        return connect_url, host_header, hostname

    async def _download(self, client: httpx.AsyncClient, url: str) -> tuple[str, str]:
        current_url = normalize_start_url(url)

        for redirect_count in range(self.max_redirects + 1):
            current_url, addresses = await resolve_url(
                current_url,
                allow_private_networks=self.allow_private_networks,
                resolver=self.resolver,
            )
            connect_url, host_header, sni_hostname = self._connection_url(current_url, addresses[0])
            headers = {
                "Host": host_header,
                "User-Agent": "BrowserJev/0.1 (+https://github.com/hermespromox/browserjev)",
            }
            try:
                async with client.stream(
                    "GET",
                    connect_url,
                    headers=headers,
                    follow_redirects=False,
                    extensions={"sni_hostname": sni_hostname},
                ) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise TransportError("redirect response is missing a location header")
                        if redirect_count >= self.max_redirects:
                            raise TransportError("too many redirects")
                        current_url = urljoin(current_url, location)
                        continue

                    response.raise_for_status()
                    media_type = response.headers.get("content-type", "").split(";", 1)[0]
                    media_type = media_type.strip().lower()
                    if media_type not in {"text/html", "application/xhtml+xml"}:
                        label = media_type or "missing"
                        raise UnsupportedContentType(f"unsupported response content type: {label}")

                    declared_size = response.headers.get("content-length")
                    if declared_size:
                        try:
                            too_large = int(declared_size) > self.max_response_bytes
                        except ValueError:
                            too_large = False
                        if too_large:
                            raise ResponseTooLarge(
                                f"response exceeds {self.max_response_bytes} bytes"
                            )

                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self.max_response_bytes:
                            raise ResponseTooLarge(
                                f"response exceeds {self.max_response_bytes} bytes"
                            )
                    encoding = response.encoding or "utf-8"
                    return current_url, bytes(body).decode(encoding, errors="replace")
            except UnsafeURLError:
                raise
            except TransportError:
                raise
            except httpx.HTTPError as exc:
                raise TransportError(str(exc)) from exc

        raise TransportError("too many redirects")

    async def fetch(self, url: str) -> PageSnapshot:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout, trust_env=False)
        try:
            final_url, html = await self._download(client, url)
        finally:
            if owns_client:
                await client.aclose()

        page = parse_page(
            final_url,
            html,
            max_text=self.max_text,
            max_links=self.max_links,
        )
        page.transport = self.name
        if len(page.text) < self.min_text and "<script" in html.lower():
            message = f"static response has only {len(page.text)} visible characters"
            raise JavaScriptRequired(message)
        return page
