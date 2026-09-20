import json
from typing import Any

import pytest

from browserjev.security import UnsafeURLError
from browserjev.transports.cascade import CascadeTransport
from browserjev.transports.http import JavaScriptRequired, TransportError
from browserjev.transports.lightpanda import LightpandaCDPRenderer, LightpandaTransport


class FakeRenderer:
    """Renderer returning the legacy two-tuple shape."""

    async def render(self, url):
        return "https://example.com/app", "<title>App</title><main>Rendered content</main>"


class TupleRenderer:
    """Renderer returning the current three-tuple shape."""

    def __init__(self, url, html, truncated=False):
        self.url = url
        self.html = html
        self.truncated = truncated

    async def render(self, _url):
        return self.url, self.html, self.truncated


class NoCallRenderer:
    def __init__(self):
        self.called = False

    async def render(self, url):
        self.called = True
        raise AssertionError("renderer must not run for a blocked target")


class StaticShell:
    async def fetch(self, url):
        raise JavaScriptRequired("script shell")


class StaticFailure:
    async def fetch(self, url):
        raise TransportError("dns failed")


class UnexpectedFallback:
    def __init__(self):
        self.called = False

    async def fetch(self, url):
        self.called = True
        raise AssertionError("fallback must not run")


async def public_resolver(hostname: str, port: int) -> list[str]:
    assert hostname == "example.com"
    return ["93.184.216.34"]


async def test_lightpanda_transport_renders_html_and_parses_snapshot():
    page = await LightpandaTransport(renderer=FakeRenderer(), resolver=public_resolver).fetch(
        "https://example.com"
    )
    assert page.url == "https://example.com/app"
    assert page.title == "App"
    assert page.text == "Rendered content"
    assert page.transport == "lightpanda"


async def test_cascade_escalates_from_http_to_lightpanda():
    cascade = CascadeTransport(
        [
            StaticShell(),
            LightpandaTransport(renderer=FakeRenderer(), resolver=public_resolver),
        ]
    )
    page = await cascade.fetch("https://example.com")
    assert page.transport == "lightpanda"


async def test_cascade_does_not_escalate_for_regular_transport_errors():
    fallback = UnexpectedFallback()
    cascade = CascadeTransport([StaticFailure(), fallback])

    with pytest.raises(TransportError, match="dns failed"):
        await cascade.fetch("https://example.com")

    assert fallback.called is False


async def test_lightpanda_blocks_private_targets_before_rendering():
    renderer = NoCallRenderer()
    transport = LightpandaTransport(renderer=renderer)

    with pytest.raises(UnsafeURLError):
        await transport.fetch("http://127.0.0.1/admin")

    assert renderer.called is False


async def test_lightpanda_rejects_non_http_schemes():
    transport = LightpandaTransport(renderer=NoCallRenderer())

    with pytest.raises(UnsafeURLError):
        await transport.fetch("file:///etc/passwd")


async def test_lightpanda_revalidates_the_rendered_landing_url():
    transport = LightpandaTransport(
        renderer=TupleRenderer("http://127.0.0.1/admin", "<title>x</title><main>y</main>"),
        resolver=public_resolver,
    )

    with pytest.raises(UnsafeURLError):
        await transport.fetch("https://example.com/")


async def test_lightpanda_reports_truncated_documents():
    transport = LightpandaTransport(
        renderer=TupleRenderer(
            "https://example.com/app", "<title>App</title><main>payload</main>", True
        ),
        resolver=public_resolver,
    )

    page = await transport.fetch("https://example.com/")

    assert page.truncated is True


class FakeWebSocket:
    """Minimal CDP peer recording every expression the renderer evaluates."""

    def __init__(self, html: str, url: str = "https://example.com/app"):
        self.html = html
        self.url = url
        self.expressions: list[str] = []
        self._queue: list[dict[str, Any]] = []

    async def send(self, payload: str) -> None:
        message = json.loads(payload)
        method = message["method"]
        result: dict[str, Any]
        if method == "Runtime.evaluate":
            expression = message["params"]["expression"]
            self.expressions.append(expression)
            if "readyState" in expression:
                result = {"result": {"value": "complete"}}
            else:
                body = {"url": self.url, "html": self.html, "truncated": False}
                result = {"result": {"value": json.dumps(body)}}
        elif method == "Target.createTarget":
            result = {"targetId": "T1"}
        elif method == "Target.attachToTarget":
            result = {"sessionId": "S1"}
        else:
            result = {}
        self._queue.append({"id": message["id"], "result": result})

    async def recv(self) -> str:
        return json.dumps(self._queue.pop(0))


class FakeConnection:
    def __init__(self, websocket: FakeWebSocket):
        self.websocket = websocket

    async def __aenter__(self) -> FakeWebSocket:
        return self.websocket

    async def __aexit__(self, *_exc) -> bool:
        return False


def _patched_renderer(monkeypatch, websocket: FakeWebSocket, **kwargs):
    monkeypatch.setattr(
        "browserjev.transports.lightpanda.websockets.connect",
        lambda *_args, **_kwargs: FakeConnection(websocket),
    )
    return LightpandaCDPRenderer(**kwargs)


async def test_renderer_caps_html_inside_the_browser(monkeypatch):
    websocket = FakeWebSocket("<main>ok</main>")
    renderer = _patched_renderer(monkeypatch, websocket, max_html=1024)

    await renderer.render("https://example.com/")

    extraction = websocket.expressions[-1]
    assert "1024" in extraction
    assert ".slice(" in extraction
    assert "truncated" in extraction


async def test_renderer_enforces_the_budget_even_if_the_page_lies(monkeypatch):
    """A page claiming `truncated: false` must still be capped client-side."""
    websocket = FakeWebSocket("x" * 10)
    renderer = _patched_renderer(monkeypatch, websocket, max_html=4)

    _url, html, truncated = await renderer.render("https://example.com/")

    assert html == "xxxx"
    assert truncated is True
