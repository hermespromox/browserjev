from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from .models import (
    ClassificationAnswer,
    ClassificationResult,
    CrawlConfig,
    Evidence,
    PageSnapshot,
    Question,
    Usage,
)


def _start_url(domain: str) -> str:
    value = domain.strip()
    if not value.startswith(("http://", "https://")):
        value = "https://" + value
    parsed = urlparse(value)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"


def _answer(raw: dict[str, Any]) -> ClassificationAnswer:
    kind = raw["type"]
    key = {"choice": "choice", "noul": "noul", "score": "score"}[kind]
    return ClassificationAnswer(
        type=kind,
        value=raw[key],
        confidence=raw.get("confidence"),
        probabilities=raw.get("probabilities"),
        legend=raw.get("legend"),
    )


class BrowserJev:
    def __init__(self, *, transport: Any, decisions: Any):
        self.transport = transport
        self.decisions = decisions

    @classmethod
    def default(
        cls,
        *,
        api_key: str | None = None,
        lightpanda_endpoint: str | None = None,
    ) -> BrowserJev:
        from .decisions import JevDecisionProvider
        from .transports import (
            CascadeTransport,
            HTTPTransport,
            LightpandaCDPRenderer,
            LightpandaTransport,
        )

        transport = CascadeTransport(
            [
                HTTPTransport(),
                LightpandaTransport(
                    renderer=LightpandaCDPRenderer(endpoint=lightpanda_endpoint)
                ),
            ]
        )
        return cls(transport=transport, decisions=JevDecisionProvider(api_key=api_key))

    async def classify(
        self,
        domain: str,
        *,
        questions: dict[str, Question],
        config: CrawlConfig | None = None,
    ) -> ClassificationResult:
        cfg = config or CrawlConfig()
        start = _start_url(domain)
        pages: list[PageSnapshot] = []
        visited: set[str] = set()
        next_url: str | None = start
        requested = "; ".join(question.instructions for question in questions.values())
        goal = f"Find direct website evidence needed to answer: {requested}"

        while next_url and len(pages) < cfg.max_pages:
            page = await self.transport.fetch(next_url)
            visited.add(page.url)
            pages.append(page)
            links = [link for link in page.links if link.url not in visited]
            if not links or len(pages) >= cfg.max_pages:
                break
            choice = await self.decisions.choose_next(goal=goal, pages=pages, links=links)
            if choice == "stop":
                break
            try:
                index = int(choice.removeprefix("link_"))
                next_url = links[index].url
            except (ValueError, IndexError):
                break

        raw_answers, raw_usage = await self.decisions.classify(pages=pages, questions=questions)
        return ClassificationResult(
            domain=urlparse(start).netloc,
            answers={key: _answer(value) for key, value in raw_answers.items()},
            evidence=[
                Evidence(url=page.url, title=page.title, excerpt=page.text[:500]) for page in pages
            ],
            pages_visited=len(pages),
            usage=Usage.model_validate(raw_usage),
        )
