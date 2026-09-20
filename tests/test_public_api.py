from browserjev import BrowserJev, ChoiceQuestion, NoulQuestion, question_from_dict
from browserjev.transports import CascadeTransport


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


def test_default_agent_uses_http_then_lightpanda():
    agent = BrowserJev.default(api_key="test", lightpanda_endpoint="ws://127.0.0.1:9999")
    assert isinstance(agent.transport, CascadeTransport)
    assert [transport.name for transport in agent.transport.transports] == ["httpx", "lightpanda"]
