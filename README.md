# BrowserJev

**A low-memory, non-generative web agent powered by typed decisions.**

BrowserJev accepts a domain and a classification schema, explores the website autonomously, gathers evidence, and uses [TypeSafe Jev](https://docs.typesafe.ai/) (`Noul`, `Choice`, and `Score`) to return structured decisions.

## Design

```text
domain + classification schema
             |
             v
 HTTPX + selectolax (default, browserless)
             |
       JavaScript required?
        /             \
      no              yes
      |                |
      |        Lightpanda CDP pool
      |                |
      +------> normalized page snapshot
                       |
                 candidate links
                       |
               Jev navigation choice
                       |
                 crawl / stop loop
                       |
            final typed classification
```

Chromium is an optional last-resort adapter, not the default path.

## Quick start

```bash
git clone https://github.com/hermespromox/browserjev.git
cd browserjev
uv sync --extra dev
export TYPESAFE_API_KEY="..."
export LIGHTPANDA_CDP_URL="ws://127.0.0.1:9222"
uv run browserjev example.com --questions examples/questions.json
```

The crawler first tries HTTPX + selectolax. It escalates to the configured Lightpanda CDP endpoint only when the static response looks like a JavaScript shell.

Start Lightpanda separately:

```bash
lightpanda serve --host 127.0.0.1 --port 9222 --cdp-max-connections 100 \
  --block-private-networks
```

For many domains, use the bounded-concurrency helper rather than spawning unbounded tasks:

```python
from browserjev import BrowserJev, NoulQuestion, classify_many

agent = BrowserJev.default()
results = await classify_many(
    agent,
    ["example.com", "example.org"],
    questions={"has_pricing": NoulQuestion(instructions="Does the site publish specific prices?")},
    concurrency=40,
)
```

## Python API

```python
from browserjev import BrowserJev, ChoiceQuestion, NoulQuestion

result = await BrowserJev.default().classify(
    "example.com",
    questions={
        "site_type": ChoiceQuestion(
            instructions="What kind of website is this?",
            choices={
                "cse": "Official employee committee website",
                "supplier": "Supplier selling services to employee committees",
                "other": "Anything else",
            },
        ),
        "has_ticketing": NoulQuestion(
            instructions="Does the website offer employee ticketing benefits?"
        ),
    },
)
```

## Principles

- HTTP-first: do not launch a browser for pages that static HTTP can parse.
- Lightpanda-on-demand: escalate only when JavaScript is required.
- Candidate-driven autonomy: Jev chooses among bounded, inspectable actions.
- No generative LLM dependency.
- Evidence-first results: classifications include URLs, supporting excerpts, the transport that produced each page, and whether its payload was truncated.
- Provider abstraction: TypeSafe Jev is the first backend, not a permanent lock-in.
- Strict budgets: same-origin navigation, bounded pages, depth, time, and payload size.

## Safe crawl (default)

BrowserJev is safe to expose to untrusted input out of the box. Every transport goes
through the same validation layer (`browserjev.security`) before a single byte leaves
the process:

- **HTTPS-first normalization.** Targets are parsed strictly, schemeless input is
  upgraded to `https://`, and embedded credentials, control characters, invalid
  percent escapes, and non-HTTP schemes are rejected.
- **Private-network blocklist.** Loopback, private, link-local, multicast, reserved
  and unspecified addresses are refused. `localhost` is refused explicitly.
- **DNS-rebinding protection.** The hostname is resolved once, the resulting address is
  validated, and the connection is pinned to that exact IP while the original `Host`
  header and TLS SNI are preserved. A rebinding resolver cannot swap the address
  between the check and the connection.
- **Redirect re-validation.** Every hop of a redirect chain is re-validated under the
  same policy, so a public host cannot bounce the crawler onto an internal service.
- **Browser re-validation.** Lightpanda renderers are validated before navigation *and*
  their landing URL is re-checked afterwards, because `meta refresh` and JavaScript
  navigation can move the page somewhere the request never asked for.
- **Payload budgets.** HTTP responses are streamed and aborted as soon as they exceed
  `max_response_bytes` (2 MB by default), and non-HTML content types are rejected from
  the headers. Lightpanda slices `documentElement.outerHTML` *inside the browser*, so an
  oversized document never crosses the CDP socket; the received length is checked again
  client-side, so a page cannot forge its way past the cap.
- **Resilient navigation.** A page that fails to load (5xx, timeout, dropped connection,
  a JavaScript shell with no browser available) is recorded and skipped instead of
  aborting the run. The entry point is the deliberate exception: if the start URL itself
  is unreachable there is nothing to classify, so the error propagates.

Security rejections raise `UnsafeURLError`, which is deliberately **not** a
`TransportError`: the cascade never treats a blocked target as a recoverable transport
failure, and never falls back to a less strict transport.

Opting out is explicit:

```python
from browserjev.transports import HTTPTransport, LightpandaTransport

# Only for trusted, internal crawls. Both transports need the flag.
transport = HTTPTransport(allow_private_networks=True)
browser = LightpandaTransport(allow_private_networks=True)
```

Tests can inject a deterministic resolver instead of touching the network:

```python
async def resolver(hostname: str, port: int) -> list[str]:
    return ["93.184.216.34"]


HTTPTransport(resolver=resolver)
```

## Command line

```bash
uv run browserjev example.com --questions examples/questions.json
```

Failures are reported as a single line on stderr, never a raw traceback:

| Exit code | Meaning | Message prefix |
|---|---|---|
| `0` | Success, JSON written to stdout | — |
| `1` | The target could not be reached | `could not reach the target` |
| `2` | The crawl was refused, or the questions file is invalid | `refusing this crawl` |

Pass `--debug` to re-raise with the full traceback when you need to diagnose a failure.

## Results

`classify()` returns a `ClassificationResult` you can log, store, or diff between runs:

```json
{
  "domain": "example.com",
  "answers": {
    "has_pricing": {"type": "noul", "value": true, "confidence": 0.93}
  },
  "evidence": [
    {"url": "https://example.com/pricing", "title": "Pricing", "excerpt": "…",
     "transport": "httpx", "truncated": false}
  ],
  "pages_visited": 3,
  "skipped_urls": ["https://example.com/broken"],
  "usage": {"input_tokens": 812, "output_tokens": 143}
}
```

Every evidence entry names the transport that produced it, so you can tell a static-HTML
finding from a browser-rendered one, and `truncated` tells you whether the excerpt came
from a page that hit the payload budget — never trust a negative answer derived from a
truncated page without checking. `skipped_urls` lists pages that could not be read, which
is where a "not found on the site" conclusion is most likely to be wrong.

## Verifying an install

`scripts/live_smoke.py` exercises the real network: it first asserts that fourteen
private/internal targets are refused, then crawls a live domain through the real cascade
and reports which transport served each page.

```bash
uv run python scripts/live_smoke.py swile.co
```

It needs no API key — the transport probe runs on its own, and the decision layer is
skipped with a note when credentials are absent. Use it as a post-deploy health check.

## Status

Early development. The first milestone is a tested Python MVP with HTTP crawling, Jev-guided navigation, typed classification, and a Lightpanda CDP adapter.

The public API follows semantic versioning from `0.1.0`; breaking changes bump the
minor version until `1.0.0`.

## Security

See [Safe crawl (default)](#safe-crawl-default) for the network-level guarantees.

- Never commit API keys. BrowserJev reads `TYPESAFE_API_KEY` from the environment.
- Run Lightpanda with `--block-private-networks` so the browser enforces the same
  policy as the crawler.
- Report suspected vulnerabilities by opening a private security advisory on the
  repository rather than a public issue.

## License

MIT
