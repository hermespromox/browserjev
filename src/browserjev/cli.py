from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .agent import BrowserJev
from .models import CrawlConfig, Question, question_from_dict


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
    return parser


async def _run(args: argparse.Namespace) -> str:
    questions = load_questions(args.questions)
    agent = BrowserJev.default(lightpanda_endpoint=args.lightpanda)
    result = await agent.classify(
        args.domain,
        questions=questions,
        config=CrawlConfig(max_pages=args.max_pages),
    )
    return result.model_dump_json(indent=None if args.compact else 2)


def main() -> None:
    args = build_parser().parse_args()
    print(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
