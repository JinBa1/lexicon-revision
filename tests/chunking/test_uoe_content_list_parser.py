from __future__ import annotations

import json
from pathlib import Path

from src.chunking.uoe_content_list_parser import UOEContentListParser

REPO_ROOT = Path(__file__).resolve().parents[2]
UOE_CONTENT_LIST = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "mineru"
    / "uoe"
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


def test_uoe_render_blocks_strip_mineru_bullet_prefix() -> None:
    blocks = UOEContentListParser()._mineru_block_to_render_blocks(
        {"type": "list", "list_items": ["\u0088 Bullet with $x$."]}
    )

    assert blocks == [
        {
            "type": "list",
            "marker": "bullet",
            "items": [
                [
                    {"type": "text", "text": "Bullet with "},
                    {"type": "math", "latex": "x"},
                    {"type": "text", "text": "."},
                ]
            ],
        }
    ]


def test_uoe_parser_strips_footer_blocks_and_punctuated_turn_over(
    tmp_path: Path,
) -> None:
    content_list = tmp_path / "2019937_MECE10017_content_list.json"
    content_list.write_text(
        json.dumps(
            [
                {"type": "text", "text": "Synthetic Course Title", "page_idx": 0},
                {"type": "text", "text": "MECE10017", "page_idx": 0},
                {"type": "text", "text": "May 2019", "page_idx": 0},
                {"type": "text", "text": "Question 1", "page_idx": 1},
                {
                    "type": "text",
                    "text": "a) Give one synthetic answer. (4)",
                    "page_idx": 1,
                },
                {"type": "text", "text": "Please turn over. ", "page_idx": 1},
                {"type": "footer", "text": "END OF PAPER ", "page_idx": 2},
            ]
        ),
        encoding="utf-8",
    )

    parsed_question = UOEContentListParser().parse(str(content_list))[0]

    assert parsed_question.sub_questions[0].marks == 4
    assert "Please turn over" not in parsed_question.sub_questions[0].text
    assert "END OF PAPER" not in parsed_question.sub_questions[0].text
