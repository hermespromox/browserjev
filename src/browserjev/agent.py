from __future__ import annotations

import os
from collections.abc import Mapping
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
from .security import normalize_start_url
from .transports.http import TransportError


def _start_url(domain: str) -> str:
    return normalize_start_url(domain)


def _first_unseen(links: list[Any], seen: set[str]) -> str | None:
    """First link that has been neither fetched nor already failed on."""
    for link in links:
        if link.url not in seen:
            return str(link.url)
    return None


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

        transports: list[Any] = [HTTPTransport()]
        endpoint = lightpanda_endpoint or os.getenv("LIGHTPANDA_CDP_URL")
        if endpoint:
            transports.append(
                LightpandaTransport(renderer=LightpandaCDPRenderer(endpoint=endpoint))
            )
        transport = CascadeTransport(transports)
        return cls(transport=transport, decisions=JevDecisionProvider(api_key=api_key))

    async def classify(
        self,
        domain: str,
        *,
        questions: Mapping[str, Question],
        config: CrawlConfig | None = None,
    ) -> ClassificationResult:
        cfg = config or CrawlConfig()
        start = _start_url(domain)
        pages: list[PageSnapshot] = []
        # `seen` tracks every URL we fetched *or* failed on, so an unreachable
        # page is never retried on a later lap of the crawl.
        seen: set[str] = set()
        skipped: list[str] = []
        next_url: str | None = start
        requested = "; ".join(question.instructions for question in questions.values())
        goal = f"Find direct website evidence needed to answer: {requested}"

        while next_url and len(pages) < cfg.max_pages:
            try:
                fetched = await self.transport.fetch(next_url)
            except TransportError:
                # One unreachable page must not sink an otherwise good crawl.
                # The entry point is the exception: if the start URL itself is
                # unreachable there is nothing to classify, so it propagates.
                seen.add(next_url)
                if not pages:
                    raise
                skipped.append(next_url)
                next_url = _first_unseen(pages[-1].links, seen)
                continue
            page = fetched.model_copy(
                update={
                    "text": fetched.text[: cfg.max_text_per_page],
                    "links": fetched.links[: cfg.max_links_per_page],
                }
            )
            seen.add(page.url)
            seen.add(next_url)
            pages.append(page)
            if len(pages) >= cfg.max_pages:
                break
            links = [link for link in page.links if link.url not in seen]
            if not links:
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
                Evidence(
                    url=page.url,
                    title=page.title,
                    excerpt=page.text[:500],
                    transport=page.transport,
                    truncated=page.truncated,
                )
                for page in pages
            ],
            pages_visited=len(pages),
            skipped_urls=skipped,
            usage=Usage.model_validate(raw_usage),
        )
