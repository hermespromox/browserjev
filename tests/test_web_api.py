from __future__ import annotations

import pytest
from pydantic import ValidationError

from browserjev import ChoiceQuestion, NoulQuestion, ScoreQuestion
from browserjev.web_api import AnalysisRequest, parse_analysis_payload


def test_parse_noul_question_uses_a_server_owned_identifier():
    request, questions = parse_analysis_payload(
        {
            "target": "example.com",
            "questions": [
                {
                    "type": "noul",
                    "instructions": "Le site affiche-t-il ses tarifs ?",
                }
            ],
        }
    )

    assert request.target == "example.com"
    assert list(questions) == ["question_1"]
    assert isinstance(questions["question_1"], NoulQuestion)


def test_parse_choice_question_builds_the_exact_jev_choice_map():
    _request, questions = parse_analysis_payload(
        {
            "target": "example.com",
            "questions": [
                {
                    "type": "choice",
                    "instructions": "Quel type de site est-ce ?",
                    "options": [
                        {"value": "éditeur", "description": "Éditeur de logiciel"},
                        {"value": "agence", "description": "Agence de services"},
                    ],
                }
            ],
        }
    )

    question = questions["question_1"]
    assert isinstance(question, ChoiceQuestion)
    assert question.choices == {
        "éditeur": "Éditeur de logiciel",
        "agence": "Agence de services",
    }


def test_parse_score_question_preserves_level_order():
    _request, questions = parse_analysis_payload(
        {
            "target": "example.com",
            "questions": [
                {
                    "type": "score",
                    "instructions": "Évalue la maturité du produit.",
                    "levels": ["Faible", "Moyenne", "Élevée"],
                }
            ],
        }
    )

    question = questions["question_1"]
    assert isinstance(question, ScoreQuestion)
    assert question.levels == ["Faible", "Moyenne", "Élevée"]


@pytest.mark.parametrize(
    "question",
    [
        {
            "type": "choice",
            "instructions": "Question valide",
            "options": [{"value": "oui", "description": "Oui"}],
        },
        {
            "type": "choice",
            "instructions": "Question valide",
            "options": [
                {"value": "même", "description": "Premier"},
                {"value": "même", "description": "Doublon"},
            ],
        },
        {
            "type": "score",
            "instructions": "Question valide",
            "levels": ["Unique"],
        },
    ],
)
def test_invalid_type_specific_parameters_are_rejected(question):
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate({"target": "example.com", "questions": [question]})


def test_unknown_fields_and_client_owned_crawl_budgets_are_rejected():
    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(
            {
                "target": "example.com",
                "max_pages": 100,
                "questions": [
                    {
                        "type": "noul",
                        "instructions": "Le site affiche-t-il ses tarifs ?",
                    }
                ],
            }
        )


def test_no_more_than_eight_questions_are_accepted():
    payload = {
        "target": "example.com",
        "questions": [
            {"type": "noul", "instructions": f"Question numéro {index} ?"} for index in range(9)
        ],
    }

    with pytest.raises(ValidationError):
        AnalysisRequest.model_validate(payload)
