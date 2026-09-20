import json

import httpx

from browserjev.decisions.jev import JevDecisionProvider
from browserjev.models import ChoiceQuestion, LinkCandidate, PageSnapshot


async def test_jev_provider_chooses_link_and_compiles_final_questions():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert request.headers["authorization"] == "Bearer test-key"
        if "next_action" in payload["questions"]:
            assert payload["questions"]["next_action"]["criteria"]["link_0"]["url"] == (
                "https://example.com/about"
            )
            return httpx.Response(
                200,
                json={
                    "model": "jev-test",
                    "answers": {
                        "next_action": {
                            "type": "choice",
                            "choice": "link_0",
                            "probabilities": {"link_0": 0.9, "stop": 0.1},
                            "confidence": 0.8,
                        }
                    },
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
                request=request,
            )
        assert payload["questions"]["kind"]["type"] == "choice"
        return httpx.Response(
            200,
            json={
                "model": "jev-test",
                "answers": {
                    "kind": {
                        "type": "choice",
                        "choice": "official",
                        "probabilities": {"official": 1.0},
                        "confidence": 1.0,
                    }
                },
                "usage": {"input_tokens": 20, "output_tokens": 3},
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = JevDecisionProvider(api_key="test-key", client=client)
        pages = [PageSnapshot(url="https://example.com", title="Home", text="Welcome")]
        links = [LinkCandidate(url="https://example.com/about", label="About")]
        selected = await provider.choose_next(goal="Find company type", pages=pages, links=links)
        answers, usage = await provider.classify(
            pages=pages,
            questions={
                "kind": ChoiceQuestion(
                    instructions="What kind?",
                    choices={"official": "Official", "other": "Other"},
                )
            },
        )

    assert selected == "link_0"
    assert answers["kind"]["choice"] == "official"
    assert usage == {"input_tokens": 20, "output_tokens": 3}
    assert len(requests) == 2
