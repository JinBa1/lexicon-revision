from __future__ import annotations

import json
from pathlib import Path

from scripts.inspect_pipeline import (
    filter_chunks,
    filter_parsed_questions,
    load_parsed_questions,
    render_json,
    render_parser_text,
    render_text,
)
from src.chunking.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")
METADATA_PATH = str(REPO_ROOT / "data" / "papers" / "metadata.json")


def _load_chunks():
    return run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        metadata_path=METADATA_PATH,
        university="cam",
    )


def test_filter_chunks_by_question_and_level() -> None:
    chunks = _load_chunks()

    filtered = filter_chunks(chunks, year=2025, paper=1, question=7, level="question")

    assert len(filtered) == 1
    assert filtered[0].id == "cam-2025-p1-q7"


def test_render_text_summary_includes_preview() -> None:
    chunks = _load_chunks()
    filtered = filter_chunks(chunks, year=2025, paper=1, question=1, level="question")

    output = render_text(filtered, view="summary", max_text_chars=80)

    assert "Matched 1 chunk(s)." in output
    assert "cam-2025-p1-q1 [question]" in output
    assert "text:" in output


def test_render_text_full_includes_media_paths_when_present() -> None:
    chunks = _load_chunks()
    filtered = filter_chunks(chunks, year=2018, paper=1, question=4, level="question")

    output = render_text(filtered, view="full", max_text_chars=200)

    assert "media paths:" in output
    assert ".jpg" in output


def test_render_json_returns_serialized_chunks() -> None:
    chunks = _load_chunks()
    filtered = filter_chunks(
        chunks,
        year=2025,
        paper=1,
        question=3,
        level="sub_question",
    )

    payload = json.loads(render_json(filtered))

    assert len(payload) == 2
    assert all(item["chunk_level"] == "sub_question" for item in payload)
    assert {item["sub_question_label"] for item in payload} == {"a", "b"}


def test_filter_parsed_questions_by_source_pdf() -> None:
    parsed_items = load_parsed_questions(MINERU_FIXTURES)

    filtered = filter_parsed_questions(
        parsed_items,
        source_pdf="y2018p5q7.pdf",
    )

    assert len(filtered) == 1
    assert filtered[0]["parsed_question"].question_number == 7


def test_render_parser_text_shows_sub_question_labels() -> None:
    parsed_items = load_parsed_questions(MINERU_FIXTURES)
    filtered = filter_parsed_questions(
        parsed_items,
        source_pdf="y2025p1q3.pdf",
    )

    output = render_parser_text(filtered, view="summary", max_text_chars=80)

    assert "Matched 1 parsed question(s)." in output
    assert "labels: ['a', 'b']" in output


def test_render_parser_json_returns_serialized_questions() -> None:
    parsed_items = load_parsed_questions(MINERU_FIXTURES)
    filtered = filter_parsed_questions(
        parsed_items,
        source_pdf="y2018p1q4.pdf",
    )

    payload = json.loads(render_json([item["parsed_question"] for item in filtered]))

    assert len(payload) == 1
    assert payload[0]["question_number"] == 4
    assert payload[0]["has_figure"] is True
