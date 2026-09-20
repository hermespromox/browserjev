from browserjev.transports.cascade import CascadeTransport
from browserjev.transports.http import JavaScriptRequired
from browserjev.transports.lightpanda import LightpandaTransport


class FakeRenderer:
    async def render(self, url):
        return "https://example.com/app", "<title>App</title><main>Rendered content</main>"


class StaticShell:
    async def fetch(self, url):
        raise JavaScriptRequired("script shell")


async def test_lightpanda_transport_renders_html_and_parses_snapshot():
    page = await LightpandaTransport(renderer=FakeRenderer()).fetch("https://example.com")
    assert page.url == "https://example.com/app"
    assert page.title == "App"
    assert page.text == "Rendered content"
    assert page.transport == "lightpanda"


async def test_cascade_escalates_from_http_to_lightpanda():
    cascade = CascadeTransport([StaticShell(), LightpandaTransport(renderer=FakeRenderer())])
    page = await cascade.fetch("https://example.com")
    assert page.transport == "lightpanda"
