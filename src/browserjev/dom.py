from __future__ import annotations

import re
from urllib.parse import urldefrag, urljoin, urlparse

from selectolax.parser import HTMLParser

from .models import LinkCandidate, PageSnapshot

_SPACE = re.compile(r"\s+")


def _clean(value: str | None) -> str:
    return _SPACE.sub(" ", value or "").strip()


def parse_page(url: str, html: str, *, max_text: int = 20_000, max_links: int = 40) -> PageSnapshot:
    tree = HTMLParser(html)
    for selector in ("script", "style", "noscript", "template"):
        for node in tree.css(selector):
            node.decompose()

    title_node = tree.css_first("title")
    title = _clean(title_node.text() if title_node else "")
    body = tree.body or tree.root
    text = _clean(body.text(separator=" ") if body else "")[:max_text]

    origin = urlparse(url).netloc.lower()
    seen: set[str] = set()
    links: list[LinkCandidate] = []
    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        absolute, _fragment = urldefrag(urljoin(url, href))
        parsed = urlparse(absolute)
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() != origin:
            continue
        if absolute in seen:
            continue
        label = _clean(node.text(separator=" ")) or _clean(node.attributes.get("aria-label"))
        if not label:
            continue
        seen.add(absolute)
        links.append(LinkCandidate(url=absolute, label=label[:300]))
        if len(links) >= max_links:
            break

    return PageSnapshot(url=url, title=title, text=text, links=links)
