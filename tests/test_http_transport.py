import httpx
import pytest

from browserjev.transports.http import HTTPTransport, JavaScriptRequired


async def public_resolver(hostname: str, port: int) -> list[str]:
    assert hostname == "example.com"
    assert port == 443
    return ["93.184.216.34"]


async def test_http_transport_fetches_and_parses_static_page():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"].startswith("BrowserJev/")
        html = (
            '<title>Home</title><main>Official employee committee</main><a href="/about">About</a>'
        )
        return httpx.Response(
            200,
            text=html,
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        page = await HTTPTransport(client=client, resolver=public_resolver).fetch(
            "https://example.com/"
        )

    assert page.title == "Home"
    assert page.transport == "httpx"
    assert page.links[0].url == "https://example.com/about"


async def test_http_transport_requests_browser_escalation_for_script_shell():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text='<html><body><div id="root"></div><script src="app.js"></script></body></html>',
            headers={"content-type": "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JavaScriptRequired):
            await HTTPTransport(
                client=client,
                min_text=20,
                resolver=public_resolver,
            ).fetch("https://example.com/")
