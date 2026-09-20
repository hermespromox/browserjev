from browserjev import BrowserJev, ChoiceQuestion, NoulQuestion, question_from_dict
from browserjev.transports import CascadeTransport


def test_error_types_are_part_of_the_public_api():
    """Callers must be able to catch security and transport failures without
    reaching into private modules."""
    import browserjev

    assert issubclass(browserjev.UnsafeURLError, ValueError)
    assert issubclass(browserjev.TransportError, RuntimeError)
    assert issubclass(browserjev.JavaScriptRequired, browserjev.TransportError)
    # A blocked target must never be caught by an except TransportError clause.
    assert not issubclass(browserjev.UnsafeURLError, browserjev.TransportError)


def test_question_from_dict_builds_typed_questions():
    choice = question_from_dict(
        {
            "type": "choice",
            "instructions": "Classify the website",
            "choices": {"official": "Official site", "other": "Other"},
        }
    )
    boolean = question_from_dict({"type": "noul", "instructions": "Has pricing?"})
    assert isinstance(choice, ChoiceQuestion)
    assert isinstance(boolean, NoulQuestion)


def test_default_agent_uses_http_then_lightpanda_when_explicitly_configured():
    agent = BrowserJev.default(api_key="test", lightpanda_endpoint="ws://127.0.0.1:9999")
    assert isinstance(agent.transport, CascadeTransport)
    assert [transport.name for transport in agent.transport.transports] == ["httpx", "lightpanda"]


def test_default_agent_is_http_only_without_lightpanda_configuration(monkeypatch):
    monkeypatch.delenv("LIGHTPANDA_CDP_URL", raising=False)
    agent = BrowserJev.default(api_key="test")
    assert isinstance(agent.transport, CascadeTransport)
    assert [transport.name for transport in agent.transport.transports] == ["httpx"]
