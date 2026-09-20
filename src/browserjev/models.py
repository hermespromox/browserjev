from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChoiceQuestion(BaseModel):
    instructions: str
    choices: dict[str, Any]

    def to_jev(self) -> dict[str, Any]:
        return {"type": "choice", "instructions": self.instructions, "criteria": self.choices}


class NoulQuestion(BaseModel):
    instructions: str
    criteria: dict[str, Any] | None = None

    def to_jev(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": "noul", "instructions": self.instructions}
        if self.criteria is not None:
            result["criteria"] = self.criteria
        return result


class ScoreQuestion(BaseModel):
    instructions: str
    levels: list[Any] = Field(min_length=2, max_length=10)

    def to_jev(self) -> dict[str, Any]:
        return {"type": "score", "instructions": self.instructions, "criteria": self.levels}


Question = ChoiceQuestion | NoulQuestion | ScoreQuestion


class LinkCandidate(BaseModel):
    url: str
    label: str


class PageSnapshot(BaseModel):
    url: str
    title: str = ""
    text: str = ""
    links: list[LinkCandidate] = Field(default_factory=list)
    transport: str = "unknown"


class CrawlConfig(BaseModel):
    max_pages: int = Field(default=8, ge=1, le=100)
    max_text_per_page: int = Field(default=20_000, ge=100, le=200_000)
    max_links_per_page: int = Field(default=40, ge=1, le=255)


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0


class ClassificationAnswer(BaseModel):
    type: Literal["choice", "noul", "score"]
    value: str | float | bool
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    legend: dict[str, str] | None = None


class Evidence(BaseModel):
    url: str
    title: str
    excerpt: str


class ClassificationResult(BaseModel):
    domain: str
    answers: dict[str, ClassificationAnswer]
    evidence: list[Evidence]
    pages_visited: int
    usage: Usage = Field(default_factory=Usage)
