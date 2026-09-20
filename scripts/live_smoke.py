"""Live smoke test: real sites, real transports, no mocks.

Run with:
    uv run python scripts/live_smoke.py example.com

Prints an auditable line per step: which transport produced the page, the
payload size, whether it was truncated, and whether each security guard held.
"""

from __future__ import annotations

import asyncio
import sys

from browserjev import BrowserJev, CrawlConfig
from browserjev.models import NoulQuestion, PageSnapshot
from browserjev.security import UnsafeURLError, validate_public_url
from browserjev.transports import (
    CascadeTransport,
    HTTPTransport,
    LightpandaTransport,
    TransportError,
)

BLOCKED_TARGETS = [
    "127.0.0.1",
    "localhost",
    "169.254.169.254",
    "http://[::1]/",
    "http://10.0.0.1/",
    "http://192.168.1.1/",
    "http://172.16.0.1/",
    "http://0.0.0.0/",
    "http://metadata.google.internal/",
    "user:pass@example.com",
    "file:///etc/passwd",
    "gopher://example.com",
    "http://127.1/",
    "http://2130706433/",
]


async def check_guards() -> int:
    failures = 0
    for target in BLOCKED_TARGETS:
        try:
            url = await validate_public_url(target)
        except UnsafeURLError as exc:
            print(f"  BLOCKED  {target:<34} -> {exc}")
        else:
            print(f"  !! HOLE  {target:<34} -> allowed as {url}")
            failures += 1
    return failures


async def crawl(domain: str) -> int:
    transport = CascadeTransport(
        [HTTPTransport(), LightpandaTransport(allow_private_networks=False)]
    )
    start = await validate_public_url(domain)
    fetched: list[PageSnapshot] = []
    skipped: list[str] = []
    seen = {start}
    next_url: str | None = start
    while next_url and len(fetched) < 3:
        try:
            page = await transport.fetch(next_url)
        except TransportError as exc:
            skipped.append(next_url)
            seen.add(next_url)
            print(f"  {'SKIPPED':<10} {next_url}  ({exc})")
            remaining = [
                link.url for link in (fetched[-1].links if fetched else []) if link.url not in seen
            ]
            next_url = remaining[0] if remaining else None
            continue
        fetched.append(page)
        seen.add(page.url)
        seen.add(next_url)
        print(
            f"  {page.transport:<10} {len(page.text):>6} chars  "
            f"{len(page.links):>3} links  truncated={page.truncated}  {page.url}"
        )
        candidates = [link.url for link in page.links if link.url not in seen]
        next_url = candidates[0] if candidates else None

    if not fetched:
        print("  no page fetched")
        return 1
    if skipped:
        print(f"  skipped {len(skipped)} unreachable page(s)")

    questions = {
        "has_pricing": NoulQuestion(instructions="Does the site publish specific prices?"),
    }
    # The decision layer needs credentials; the transport probe above does not.
    # This keeps the live smoke test usable as a pre-deploy health check.
    try:
        agent = BrowserJev.default()
        result = await agent.classify(start, questions=questions, config=CrawlConfig(max_pages=2))
    except ValueError as exc:
        print(f"  decision layer unavailable (no credentials): {exc}")
        return 0
    print(f"  answer: {result.answers['has_pricing'].value}")
    for item in result.evidence:
        print(f"    evidence: {item.transport} truncated={item.truncated} {item.url}")
    return 0


async def main() -> int:
    domain = sys.argv[1] if len(sys.argv) > 1 else "example.com"
    print("security guards:")
    failures = await check_guards()
    print(f"\nlive crawl of {domain}:")
    failures += await crawl(domain)
    print(f"\nresult: {'FAIL' if failures else 'OK'} ({failures} problem(s))")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
