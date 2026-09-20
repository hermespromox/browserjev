import json

import pytest

from browserjev.cli import build_parser, load_questions, main
from browserjev.models import ChoiceQuestion, NoulQuestion
from browserjev.security import UnsafeURLError
from browserjev.transports.http import TransportError


@pytest.fixture()
def questions_file(tmp_path):
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
    return path


def test_load_questions_reads_generic_json_schema(questions_file):
    questions = load_questions(questions_file)
    assert isinstance(questions["site_type"], ChoiceQuestion)
    assert isinstance(questions["has_pricing"], NoulQuestion)


def test_load_questions_rejects_an_empty_object(tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("{}")

    with pytest.raises(ValueError, match="non-empty"):
        load_questions(path)


def test_parser_exposes_an_offline_safe_default():
    args = build_parser().parse_args(["example.com", "--questions", "q.json"])
    assert args.debug is False


def test_cli_reports_blocked_targets_without_a_traceback(monkeypatch, capsys, questions_file):
    async def blocked(*_args, **_kwargs):
        raise UnsafeURLError("private or local network targets are blocked")

    monkeypatch.setattr("browserjev.cli._run", blocked)

    exit_code = main(["127.0.0.1", "--questions", str(questions_file)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "private or local network targets are blocked" in captured.err
    assert "Traceback" not in captured.err


def test_cli_reports_transport_failures_without_a_traceback(monkeypatch, capsys, questions_file):
    async def unreachable(*_args, **_kwargs):
        raise TransportError("connection reset by peer")

    monkeypatch.setattr("browserjev.cli._run", unreachable)

    exit_code = main(["example.com", "--questions", str(questions_file)])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "connection reset by peer" in captured.err
    assert "Traceback" not in captured.err


def test_cli_debug_flag_surfaces_the_traceback(monkeypatch, questions_file):
    async def blocked(*_args, **_kwargs):
        raise UnsafeURLError("blocked")

    monkeypatch.setattr("browserjev.cli._run", blocked)

    with pytest.raises(UnsafeURLError):
        main(["127.0.0.1", "--questions", str(questions_file), "--debug"])


def test_cli_validates_the_target_before_requiring_credentials(monkeypatch, capsys, questions_file):
    """A blocked target must be reported as blocked, not as a missing API key."""
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)

    exit_code = main(["127.0.0.1", "--questions", str(questions_file)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "network targets are blocked" in captured.err
    assert "TYPESAFE_API_KEY" not in captured.err


def test_cli_prints_json_on_success(monkeypatch, capsys, questions_file):
    async def ok(*_args, **_kwargs):
        return {"pages_visited": 1}

    monkeypatch.setattr("browserjev.cli._run", ok)

    exit_code = main(["example.com", "--questions", str(questions_file), "--compact"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert json.loads(captured.out) == {"pages_visited": 1}
