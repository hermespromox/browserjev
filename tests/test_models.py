from browserjev.models import ChoiceQuestion, NoulQuestion, ScoreQuestion


def test_choice_question_compiles_to_jev_schema():
    question = ChoiceQuestion(
        instructions="Classify this website",
        choices={"official": "Official site", "supplier": "Commercial supplier"},
    )
    assert question.to_jev() == {
        "type": "choice",
        "instructions": "Classify this website",
        "criteria": {"official": "Official site", "supplier": "Commercial supplier"},
    }


def test_noul_and_score_questions_compile_to_jev_schema():
    assert NoulQuestion(instructions="Is it official?").to_jev() == {
        "type": "noul",
        "instructions": "Is it official?",
    }
    assert ScoreQuestion(instructions="How relevant?", levels=["none", "high"]).to_jev() == {
        "type": "score",
        "instructions": "How relevant?",
        "criteria": ["none", "high"],
    }
