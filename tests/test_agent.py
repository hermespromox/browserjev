from browserjev.agent import BrowserJev
from browserjev.models import ChoiceQuestion, CrawlConfig, PageSnapshot


class FakeTransport:
    name = "fake"

    def __init__(self):
        self.visited = []

    async def fetch(self, url):
        self.visited.append(url)
        if url.endswith("/benefits"):
            return PageSnapshot(
                url=url,
                title="Benefits",
                text="Employee ticketing and gift cards",
                links=[],
            )
        return PageSnapshot(
            url=url,
            title="Home",
            text="Welcome to ACME employee committee",
            links=[{"url": "https://acme.example/benefits", "label": "Benefits"}],
        )


class FakeDecisionProvider:
    def __init__(self):
        self.navigation_calls = 0
        self.last_goal = None

    async def choose_next(self, *, goal, pages, links):
        self.navigation_calls += 1
        self.last_goal = goal
        return "link_0" if self.navigation_calls == 1 else "stop"

    async def classify(self, *, pages, questions):
        return {
            "site_type": {
                "type": "choice",
                "choice": "cse",
                "confidence": 0.99,
                "probabilities": {"cse": 0.99, "other": 0.01},
            }
        }, {"input_tokens": 100, "output_tokens": 20}


async def test_agent_navigates_then_classifies_with_evidence():
    transport = FakeTransport()
    decisions = FakeDecisionProvider()
    agent = BrowserJev(transport=transport, decisions=decisions)
    result = await agent.classify(
        "acme.example",
        questions={
            "site_type": ChoiceQuestion(
                instructions="Classify the site",
                choices={"cse": "Employee committee", "other": "Other"},
            )
        },
        config=CrawlConfig(max_pages=3),
    )
    assert transport.visited == ["https://acme.example/", "https://acme.example/benefits"]
    assert result.answers["site_type"].value == "cse"
    assert result.pages_visited == 2
    assert [e.url for e in result.evidence] == transport.visited
    assert result.usage.input_tokens == 100
    assert "Classify the site" in decisions.last_goal
