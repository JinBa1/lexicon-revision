from __future__ import annotations

from pathlib import Path

from pydantic import TypeAdapter
from src.chunking.cambridge_content_list_parser import (
    CambridgeContentListParser,
    _strip_label_from_runs,
)
from src.chunking.mineru_segments import LogicalSegment
from src.chunking.models import ParsedQuestion, SubQuestion
from src.chunking.pipeline import _build_chunks, run_pipeline
from src.rendering.blocks import RenderBlock, flatten_render_blocks

REPO_ROOT = Path(__file__).resolve().parents[2]


def _validated_text(blocks: list[dict]) -> str:
    render_blocks = TypeAdapter(list[RenderBlock]).validate_python(blocks)
    return flatten_render_blocks(render_blocks)


def test_segment_splitter_splits_list_block_at_b_label_and_strips_labels() -> None:
    parser = CambridgeContentListParser()
    segments = parser._split_into_logical_segments(
        [
            {
                "type": "list",
                "list_items": [
                    "(a) First part with $x$.",
                    "Still part a.",
                    "(b) Second part.",
                ],
            }
        ]
    )

    assert [segment.label for segment in segments] == ["a", "b"]
    assert _validated_text(segments[0].blocks) == "First part with $x$.\nStill part a."
    assert _validated_text(segments[1].blocks) == "Second part."


def test_segment_splitter_keeps_preamble_label_none() -> None:
    parser = CambridgeContentListParser()
    segments = parser._split_into_logical_segments(
        [
            {"type": "text", "text": "Intro text."},
            {"type": "text", "text": "(a) First part."},
        ]
    )

    assert segments[0].label is None
    assert _validated_text(segments[0].blocks) == "Intro text."


def test_mineru_text_block_converts_inline_math_to_paragraph_runs() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "text", "text": "Show $x+y$ now."}
    )

    assert blocks == [
        {
            "type": "paragraph",
            "runs": [
                {"type": "text", "text": "Show "},
                {"type": "math", "latex": "x+y"},
                {"type": "text", "text": " now."},
            ],
        }
    ]


def test_mineru_equation_block_strips_outer_dollar_wrappers() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "equation", "text": "$$x = y$$"}
    )

    assert blocks == [{"type": "equation", "latex": "x = y"}]


def test_mineru_list_block_strips_bullet_glyph_prefix() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
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


def test_mineru_nested_roman_list_uses_plain_marker() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "list", "list_items": ["(i) Explain one case.", "(ii) Explain two."]}
    )

    assert blocks[0]["marker"] == "plain"


def test_mineru_numeric_list_uses_ordered_marker_and_strips_prefixes() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "list", "list_items": ["1. First.", "2. Second with $x$."]}
    )

    assert blocks[0]["marker"] == "ordered"
    assert blocks[0]["items"] == [
        [{"type": "text", "text": "First."}],
        [
            {"type": "text", "text": "Second with "},
            {"type": "math", "latex": "x"},
            {"type": "text", "text": "."},
        ],
    ]


def test_mineru_code_block_passes_code_body_through() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "code", "code_body": "print('hello')"}
    )

    assert blocks == [{"type": "code", "code": "print('hello')", "language": None}]


def test_mineru_image_block_uses_order_index_media_id() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks({"type": "image"}, order_index=7)

    assert blocks == [{"type": "image", "media_id": "image_7"}]


def test_mineru_table_block_parses_html_rows() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {
            "type": "table",
            "table_body": (
                "<table><tr><th>A</th><th>B</th></tr>"
                "<tr><td>1</td><td>2</td></tr></table>"
            ),
        },
        order_index=3,
    )

    assert blocks == [
        {
            "type": "table",
            "rows": [["A", "B"], ["1", "2"]],
            "media_id": "table_3",
        }
    ]


def test_mineru_malformed_table_falls_back_to_source_note_and_raw_text() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "table", "table_body": "not   a\n\n table"},
        order_index=3,
    )

    assert blocks == [
        {
            "type": "paragraph",
            "runs": [{"type": "text", "text": "[table — see source] not a table"}],
        }
    ]


def test_mineru_malformed_table_with_non_string_body_falls_back_to_source_note() -> (
    None
):
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "table", "table_body": None},
        order_index=3,
    )

    assert blocks == [
        {
            "type": "paragraph",
            "runs": [{"type": "text", "text": "[table — see source]"}],
        }
    ]


def test_mineru_unknown_block_with_text_becomes_paragraph() -> None:
    parser = CambridgeContentListParser()
    blocks = parser._mineru_block_to_render_blocks(
        {"type": "aside", "text": "Keep me."}
    )

    assert blocks == [
        {"type": "paragraph", "runs": [{"type": "text", "text": "Keep me."}]}
    ]


def test_mineru_unknown_block_without_text_is_dropped() -> None:
    parser = CambridgeContentListParser()
    assert parser._mineru_block_to_render_blocks({"type": "aside"}) == []


def test_segments_carry_typed_render_blocks_and_inline_math_round_trips() -> None:
    parser = CambridgeContentListParser()
    segments = parser._split_into_logical_segments(
        [{"type": "text", "text": "(a) Use $n^2$ operations."}]
    )

    assert segments[0].blocks == [
        {
            "type": "paragraph",
            "runs": [
                {"type": "text", "text": "Use "},
                {"type": "math", "latex": "n^2"},
                {"type": "text", "text": " operations."},
            ],
        }
    ]
    assert _validated_text(segments[0].blocks) == "Use $n^2$ operations."


def test_strip_label_from_runs_checks_later_text_after_non_matching_run() -> None:
    runs = [
        {"type": "math", "latex": "x"},
        {"type": "text", "text": " "},
        {"type": "text", "text": "(a) Use induction."},
    ]

    assert _strip_label_from_runs(runs) is True
    assert runs == [
        {"type": "math", "latex": "x"},
        {"type": "text", "text": " "},
        {"type": "text", "text": "Use induction."},
    ]


def test_parent_chunk_label_prefix_falls_back_before_equation_first_segment() -> None:
    parsed_question = ParsedQuestion(
        tripos_part="Part IA",
        year=2025,
        paper=1,
        question_number=1,
        topic="Topic",
        author="abc",
        preamble="",
        sub_questions=[SubQuestion(label="a", text="x = y", marks=None)],
        total_marks=None,
        has_code=False,
        has_figure=False,
        has_table=False,
    )
    segments = [
        LogicalSegment(
            label="a",
            blocks=[{"type": "equation", "latex": "x = y"}],
        )
    ]

    chunks = _build_chunks(parsed_question, {}, "q.pdf", "cam", segments)

    question = next(chunk for chunk in chunks if chunk.chunk_level == "question")
    sub_question = next(
        chunk for chunk in chunks if chunk.chunk_level == "sub_question"
    )
    assert question.render_blocks == [
        {"type": "paragraph", "runs": [{"type": "text", "text": "(a) "}]},
        {"type": "equation", "latex": "x = y"},
    ]
    assert question.text == "(a) \n\nx = y"
    assert sub_question.render_blocks == [{"type": "equation", "latex": "x = y"}]


def test_run_pipeline_populates_render_blocks_matching_chunk_text_for_q1(
    tmp_path,
) -> None:
    src = REPO_ROOT / "tests" / "fixtures" / "mineru" / "cambridge" / "y2025p1q1"
    dst = tmp_path / "y2025p1q1"
    dst.mkdir()
    (dst / "hybrid_auto").mkdir()
    fixture = src / "hybrid_auto" / "y2025p1q1_content_list.json"
    copied = dst / "hybrid_auto" / "y2025p1q1_content_list.json"
    copied.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    chunks = run_pipeline(str(tmp_path), university="cam")

    assert chunks
    for chunk in chunks:
        assert chunk.render_blocks
        render_blocks = TypeAdapter(list[RenderBlock]).validate_python(
            chunk.render_blocks
        )
        assert flatten_render_blocks(render_blocks).strip() == chunk.text.strip()
