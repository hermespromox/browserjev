from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

from .models import ClassificationResult, CrawlConfig, Question


async def classify_many(
    agent: Any,
    domains: Iterable[str],
    *,
    questions: dict[str, Question],
    concurrency: int = 20,
    config: CrawlConfig | None = None,
) -> list[ClassificationResult]:
    if concurrency < 1:
        raise ValueError("concurrency must be at least 1")
    semaphore = asyncio.Semaphore(concurrency)
    crawl_config = config or CrawlConfig()

    async def classify_one(domain: str) -> ClassificationResult:
        async with semaphore:
            return await agent.classify(domain, questions=questions, config=crawl_config)

    return await asyncio.gather(*(classify_one(domain) for domain in domains))
