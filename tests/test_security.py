import httpx
import pytest

from browserjev.security import UnsafeURLError, normalize_start_url, validate_public_url
from browserjev.transports.http import HTTPTransport, ResponseTooLarge, UnsupportedContentType


async def public_resolver(hostname: str, port: int) -> list[str]:
    assert hostname == "example.com"
    assert port == 443
    return ["93.184.216.34"]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "ftp://example.com/file",
        "https://user:***@example.com/",
        "https:///missing-host",
        "https://exa mple.com/",
        "https://%zz/",
        "https://[::1",
    ],
)
def test_normalize_start_url_rejects_invalid_targets(value):
    with pytest.raises(UnsafeURLError):
        normalize_start_url(value)


def test_normalize_start_url_preserves_query_and_removes_fragment():
    assert normalize_start_url("example.com/path?q=1#section") == "https://example.com/path?q=1"


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://224.0.0.1/",
    ],
)
async def test_validate_public_url_rejects_non_public_ip_literals(url):
    with pytest.raises(UnsafeURLError):
        await validate_public_url(url)


async def test_http_transport_revalidates_redirect_targets():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(
            302,
            headers={"location": "http://127.0.0.1/private"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsafeURLError):
            await HTTPTransport(client=client, resolver=public_resolver).fetch(
                "https://example.com/"
            )

    assert requests == ["https://93.184.216.34/"]


async def test_http_transport_reports_logical_url_after_pinned_connection():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "example.com"
        assert request.extensions["sni_hostname"] == "example.com"
        return httpx.Response(
            200,
            text='<title>Safe</title><a href="/about">About</a>',
            headers={"content-type": "text/html; charset=utf-8"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        page = await HTTPTransport(client=client, resolver=public_resolver).fetch(
            "https://example.com/"
        )

    assert page.url == "https://example.com/"
    assert page.links[0].url == "https://example.com/about"


async def test_http_transport_rejects_oversized_stream_before_parsing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html>" + b"x" * 200 + b"</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ResponseTooLarge):
            await HTTPTransport(
                client=client,
                max_response_bytes=100,
                resolver=public_resolver,
            ).fetch("https://example.com/")


async def test_http_transport_rejects_non_html_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"%PDF-1.7",
            headers={"content-type": "application/pdf"},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsupportedContentType):
            await HTTPTransport(client=client, resolver=public_resolver).fetch(
                "https://example.com/file.pdf"
            )


@pytest.mark.parametrize("content_type", ["text/plain", "text/html-malicious", ""])
async def test_http_transport_requires_an_exact_html_media_type(content_type):
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(200, text="not declared html", headers=headers, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(UnsupportedContentType):
            await HTTPTransport(client=client, resolver=public_resolver).fetch(
                "https://example.com/"
            )
