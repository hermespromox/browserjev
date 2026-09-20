from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .agent import BrowserJev
from .models import (
    ChoiceQuestion,
    ClassificationResult,
    CrawlConfig,
    NoulQuestion,
    Question,
    ScoreQuestion,
)

Instruction = Annotated[str, Field(min_length=3, max_length=500)]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class ChoiceOptionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    value: Annotated[str, Field(min_length=1, max_length=60)]
    description: Annotated[str, Field(min_length=1, max_length=240)]


class NoulQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["noul"]
    instructions: Instruction


class ChoiceQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["choice"]
    instructions: Instruction
    options: Annotated[list[ChoiceOptionInput], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def require_unique_values(self) -> ChoiceQuestionInput:
        values = [option.value.casefold() for option in self.options]
        if len(values) != len(set(values)):
            raise ValueError("choice option values must be unique")
        return self


class ScoreQuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    type: Literal["score"]
    instructions: Instruction
    levels: Annotated[list[ShortText], Field(min_length=2, max_length=10)]

    @field_validator("levels")
    @classmethod
    def require_unique_levels(cls, values: list[str]) -> list[str]:
        normalized = [value.casefold() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("score levels must be unique")
        return values


QuestionInput = Annotated[
    NoulQuestionInput | ChoiceQuestionInput | ScoreQuestionInput,
    Field(discriminator="type"),
]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target: Annotated[str, Field(min_length=3, max_length=2048)]
    questions: Annotated[list[QuestionInput], Field(min_length=1, max_length=8)]

    def to_questions(self) -> dict[str, Question]:
        parsed: dict[str, Question] = {}
        for index, question in enumerate(self.questions, start=1):
            key = f"question_{index}"
            if isinstance(question, NoulQuestionInput):
                parsed[key] = NoulQuestion(instructions=question.instructions)
            elif isinstance(question, ChoiceQuestionInput):
                parsed[key] = ChoiceQuestion(
                    instructions=question.instructions,
                    choices={option.value: option.description for option in question.options},
                )
            else:
                parsed[key] = ScoreQuestion(
                    instructions=question.instructions,
                    levels=question.levels,
                )
        return parsed


WEB_CRAWL_CONFIG = CrawlConfig(max_pages=6, max_text_per_page=15_000, max_links_per_page=30)


def parse_analysis_payload(payload: Any) -> tuple[AnalysisRequest, dict[str, Question]]:
    request = AnalysisRequest.model_validate(payload)
    return request, request.to_questions()


async def classify_analysis_payload(
    payload: Any,
    *,
    api_key: str | None = None,
    agent: BrowserJev | None = None,
) -> ClassificationResult:
    request, questions = parse_analysis_payload(payload)
    classifier = agent or BrowserJev.default(api_key=api_key)
    return await classifier.classify(
        request.target,
        questions=questions,
        config=WEB_CRAWL_CONFIG,
    )
