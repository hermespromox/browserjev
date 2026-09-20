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
- Evidence-first results: classifications include URLs and supporting excerpts.
- Provider abstraction: TypeSafe Jev is the first backend, not a permanent lock-in.
- Strict budgets: same-origin navigation, bounded pages, depth, time, and payload size.

## Status

Early development. The first milestone is a tested Python MVP with HTTP crawling, Jev-guided navigation, typed classification, and a Lightpanda CDP adapter.

## Security

Never commit API keys. BrowserJev reads `TYPESAFE_API_KEY` from the environment.

## License

MIT
