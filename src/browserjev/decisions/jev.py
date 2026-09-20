from __future__ import annotations

import os
from typing import Any

import httpx

from ..models import LinkCandidate, PageSnapshot, Question


class JevError(RuntimeError):
    pass


class JevDecisionProvider:
    endpoint = "https://api.typesafe.ai/v1/systemone"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        model: str = "jev-latest",
        timeout: float = 30.0,
    ):
        self.api_key = api_key or os.getenv("TYPESAFE_API_KEY")
        if not self.api_key:
            raise ValueError("TYPESAFE_API_KEY is required")
        self._client = client
        self.model = model
        self.timeout = timeout

    @staticmethod
    def _state(pages: list[PageSnapshot], *, goal: str | None = None) -> dict[str, Any]:
        state: dict[str, Any] = {
            "pages": [
                {"url": page.url, "title": page.title, "text": page.text} for page in pages
            ]
        }
        if goal:
            state["goal"] = goal
        return state

    async def _evaluate(self, *, state: Any, questions: dict[str, Any]) -> dict[str, Any]:
        payload = {"state": state, "model": self.model, "questions": questions}
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            response = await client.post(
                self.endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise JevError(f"TypeSafe Jev request failed: {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        if not isinstance(data.get("answers"), dict):
            raise JevError("TypeSafe Jev response is missing answers")
        return data

    async def choose_next(
        self,
        *,
        goal: str,
        pages: list[PageSnapshot],
        links: list[LinkCandidate],
    ) -> str:
        criteria: dict[str, Any] = {
            f"link_{index}": {"url": link.url, "label": link.label}
            for index, link in enumerate(links)
        }
        criteria["stop"] = "Stop when the collected pages are sufficient to answer the goal."
        data = await self._evaluate(
            state=self._state(pages, goal=goal),
            questions={
                "next_action": {
                    "type": "choice",
                    "instructions": (
                        "Choose the single link most likely to provide missing direct evidence, "
                        "or stop when enough evidence has already been collected."
                    ),
                    "criteria": criteria,
                }
            },
        )
        answer = data["answers"].get("next_action", {})
        choice = answer.get("choice")
        return choice if isinstance(choice, str) and choice in criteria else "stop"

    async def classify(
        self,
        *,
        pages: list[PageSnapshot],
        questions: dict[str, Question],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        data = await self._evaluate(
            state=self._state(pages),
            questions={key: question.to_jev() for key, question in questions.items()},
        )
        return data["answers"], data.get("usage", {})
