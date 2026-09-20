from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .agent import BrowserJev
from .models import CrawlConfig, Question, question_from_dict
from .security import UnsafeURLError, validate_public_url
from .transports.http import TransportError

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2


def load_questions(path: Path) -> dict[str, Question]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not raw:
        raise ValueError("questions file must contain a non-empty JSON object")
    return {name: question_from_dict(data) for name, data in raw.items()}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="browserjev",
        description="Autonomously navigate and classify a website with typed Jev decisions.",
    )
    parser.add_argument("domain", help="Domain or starting URL")
    parser.add_argument("--questions", type=Path, required=True, help="JSON question schema")
    parser.add_argument("--max-pages", type=int, default=8)
    parser.add_argument("--lightpanda", help="Lightpanda browser WebSocket CDP endpoint")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Re-raise failures with a full traceback instead of a one-line report",
    )
    return parser


async def _run(args: argparse.Namespace) -> Any:
    questions = load_questions(args.questions)
    # Validate the target before touching credentials: a refused crawl should be
    # reported as refused, not as a missing API key.
    start_url = await validate_public_url(args.domain)
    agent = BrowserJev.default(lightpanda_endpoint=args.lightpanda)
    result = await agent.classify(
        start_url,
        questions=questions,
        config=CrawlConfig(max_pages=args.max_pages),
    )
    return result.model_dump_json(indent=None if args.compact else 2)


def _render(payload: Any, *, compact: bool) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, indent=None if compact else 2)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(_run(args))
    except (UnsafeURLError, ValueError) as exc:
        if args.debug:
            raise
        print(f"browserjev: refusing this crawl: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    except TransportError as exc:
        if args.debug:
            raise
        print(f"browserjev: could not reach the target: {exc}", file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    print(_render(payload, compact=args.compact))
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
