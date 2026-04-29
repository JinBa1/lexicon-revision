from __future__ import annotations

from pathlib import Path

from src.chunking.uoe_content_list_parser import UOEContentListParser

REPO_ROOT = Path(__file__).resolve().parents[2]
UOE_CONTENT_LIST = (
    REPO_ROOT
    / "tests"
    / "data"
    / "uoe_mineru_fixtures"
    / "2019937_MECE10017"
    / "hybrid_auto"
    / "2019937_MECE10017_content_list.json"
)


def test_uoe_parser_extracts_cover_metadata_and_multiple_questions() -> None:
    parsed_questions = UOEContentListParser().parse(str(UOE_CONTENT_LIST))

    assert len(parsed_questions) == 2
    first_question = parsed_questions[0]
    assert first_question.year == 2019
    assert first_question.metadata == {
        "course_code": "MECE10017",
        "course_title": "DESIGN OF SURGICAL TOOLS AND IMPLANTED MEDICAL DEVICES MSC",
        "document_id": "2019937",
    }


def test_uoe_parser_splits_top_level_sub_questions_only() -> None:
    first_question = UOEContentListParser().parse(str(UOE_CONTENT_LIST))[0]

    assert [sub.label for sub in first_question.sub_questions] == ["a", "b"]
    sub_b = first_question.sub_questions[1]
    assert "(i) first nested point" in sub_b.text
    assert "(ii) second nested point" in sub_b.text


def test_uoe_parser_extracts_marks_after_footer_stripping() -> None:
    first_question, second_question = UOEContentListParser().parse(
        str(UOE_CONTENT_LIST)
    )

    assert [sub.marks for sub in first_question.sub_questions] == [6, 4]
    assert [sub.marks for sub in second_question.sub_questions] == [5]
    assert "(4)" not in first_question.sub_questions[1].text
    assert first_question.total_marks == 10
    assert second_question.total_marks == 5


def test_uoe_parser_strips_footer_phrases_from_text() -> None:
    parsed_questions = UOEContentListParser().parse(str(UOE_CONTENT_LIST))
    text_parts = []
    for question in parsed_questions:
        text_parts.append(question.preamble)
        text_parts.extend(sub.text for sub in question.sub_questions)
    all_text = "\n".join(text_parts)

    assert "Please turn over" not in all_text
    assert "END OF PAPER" not in all_text
