import asyncio

from browserjev.batch import classify_many
from browserjev.models import NoulQuestion


class FakeAgent:
    def __init__(self):
        self.active = 0
        self.peak = 0

    async def classify(self, domain, *, questions, config):
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return domain


async def test_classify_many_preserves_order_and_bounds_concurrency():
    agent = FakeAgent()
    domains = [f"site-{index}.example" for index in range(8)]
    results = await classify_many(
        agent,
        domains,
        questions={"relevant": NoulQuestion(instructions="Is it relevant?")},
        concurrency=3,
    )
    assert results == domains
    assert agent.peak == 3
