import pytest

from browserjev.agent import BrowserJev
from browserjev.models import ChoiceQuestion, CrawlConfig, PageSnapshot
from browserjev.transports.http import TransportError


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
                transport="lightpanda",
                truncated=True,
            )
        return PageSnapshot(
            url=url,
            title="Home",
            text=("Welcome to ACME employee committee and its complete member services. " * 4),
            links=[
                {"url": "https://acme.example/benefits", "label": "Benefits"},
                {"url": "https://acme.example/contact", "label": "Contact"},
            ],
            transport="httpx",
        )


class FakeDecisionProvider:
    def __init__(self):
        self.navigation_calls = 0
        self.last_goal = None
        self.classification_pages = None

    async def choose_next(self, *, goal, pages, links):
        self.navigation_calls += 1
        self.last_goal = goal
        return "link_0" if self.navigation_calls == 1 else "stop"

    async def classify(self, *, pages, questions):
        self.classification_pages = pages
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
    assert result.evidence[0].transport == "httpx"
    assert result.evidence[1].transport == "lightpanda"
    assert result.evidence[1].truncated is True


async def test_agent_applies_text_and_link_budgets_before_decisions():
    transport = FakeTransport()
    decisions = FakeDecisionProvider()
    agent = BrowserJev(transport=transport, decisions=decisions)

    await agent.classify(
        "acme.example",
        questions={
            "site_type": ChoiceQuestion(
                instructions="Classify the site",
                choices={"cse": "Employee committee", "other": "Other"},
            )
        },
        config=CrawlConfig(max_pages=1, max_text_per_page=100, max_links_per_page=1),
    )

    assert decisions.classification_pages is not None
    assert len(decisions.classification_pages[0].text) == 100
    assert len(decisions.classification_pages[0].links) == 1


class OneBrokenLinkTransport:
    """The first candidate link 500s; the second one is fine."""

    name = "fake"

    def __init__(self):
        self.visited = []

    async def fetch(self, url):
        self.visited.append(url)
        if url.endswith("/broken"):
            raise TransportError("Server error '500 Internal Server Error'")
        if url.endswith("/benefits"):
            return PageSnapshot(
                url=url,
                title="Benefits",
                text="Employee ticketing and gift cards",
                links=[],
                transport="httpx",
            )
        return PageSnapshot(
            url=url,
            title="Home",
            text=("Welcome to ACME employee committee and its complete member services. " * 4),
            links=[
                {"url": "https://acme.example/broken", "label": "Broken"},
                {"url": "https://acme.example/benefits", "label": "Benefits"},
            ],
            transport="httpx",
        )


class AlwaysBrokenTransport:
    name = "fake"

    async def fetch(self, url):
        raise TransportError("Server error '500 Internal Server Error'")


async def test_agent_skips_a_broken_page_and_keeps_crawling():
    transport = OneBrokenLinkTransport()
    agent = BrowserJev(transport=transport, decisions=FakeDecisionProvider())

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

    assert transport.visited == [
        "https://acme.example/",
        "https://acme.example/broken",
        "https://acme.example/benefits",
    ]
    assert [page.url for page in result.evidence] == [
        "https://acme.example/",
        "https://acme.example/benefits",
    ]
    assert result.skipped_urls == ["https://acme.example/broken"]
    assert result.answers["site_type"].value == "cse"


async def test_agent_still_fails_when_the_entry_point_is_unreachable():
    agent = BrowserJev(transport=AlwaysBrokenTransport(), decisions=FakeDecisionProvider())

    with pytest.raises(TransportError, match="500"):
        await agent.classify(
            "acme.example",
            questions={
                "site_type": ChoiceQuestion(
                    instructions="Classify the site",
                    choices={"cse": "Employee committee", "other": "Other"},
                )
            },
        )
