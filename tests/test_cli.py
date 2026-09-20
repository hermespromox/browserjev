import json

from browserjev.cli import load_questions
from browserjev.models import ChoiceQuestion, NoulQuestion


def test_load_questions_reads_generic_json_schema(tmp_path):
    path = tmp_path / "questions.json"
    path.write_text(
        json.dumps(
            {
                "site_type": {
                    "type": "choice",
                    "instructions": "Classify the site",
                    "choices": {"official": "Official", "other": "Other"},
                },
                "has_pricing": {
                    "type": "noul",
                    "instructions": "Does the site publish pricing?",
                },
            }
        )
    )
    questions = load_questions(path)
    assert isinstance(questions["site_type"], ChoiceQuestion)
    assert isinstance(questions["has_pricing"], NoulQuestion)
