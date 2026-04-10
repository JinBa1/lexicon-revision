from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts.inspect_pipeline import (
    filter_chunks,
    filter_parsed_questions,
    load_parsed_questions,
    main,
    render_json,
    render_parser_text,
    render_text,
)
from src.chunking.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")


def _load_chunks():
    return run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )


def _run_cli(monkeypatch, capsys, *args: str) -> str:
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_pipeline.py", *args],
    )
    main()
    return capsys.readouterr().out


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

    assert "media:" in output
    assert ".jpg" in output


def test_render_text_full_includes_enriched_media_debug_fields() -> None:
    chunks = _load_chunks()
    filtered = filter_chunks(chunks, year=2018, paper=8, question=7, level="question")

    output = render_text(filtered, view="full", max_text_chars=200)

    assert "kind=table" in output
    assert "relation=visible_from_child" in output
    assert "owner_level=sub_question" in output
    assert "owner_label=b" in output
    assert "page_number=1" in output
    assert "media_id=table_2" in output
    assert "order_index=2" in output
    assert "bbox=(247.0, 472.0, 771.0, 545.0)" in output
    assert "text_payload=present" in output
    assert "text_payload_len=" in output


def test_cli_full_text_output_includes_enriched_media_fields(
    monkeypatch,
    capsys,
) -> None:
    output = _run_cli(
        monkeypatch,
        capsys,
        MINERU_FIXTURES,
        "--year",
        "2018",
        "--paper",
        "8",
        "--question",
        "7",
        "--level",
        "question",
        "--view",
        "full",
    )

    assert "Matched 1 chunk(s)." in output
    assert "kind=table" in output
    assert "relation=visible_from_child" in output
    assert "owner_level=sub_question" in output
    assert "owner_label=b" in output
    assert "page_number=1" in output
    assert "media_id=table_2" in output
    assert "order_index=2" in output
    assert "bbox=(247.0, 472.0, 771.0, 545.0)" in output
    assert "text_payload=present" in output
    assert "text_payload_len=" in output


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


def test_render_json_exposes_enriched_media_metadata() -> None:
    chunks = _load_chunks()
    filtered = filter_chunks(chunks, year=2018, paper=8, question=7, level="question")

    payload = json.loads(render_json(filtered))

    assert len(payload) == 1
    media_ref = payload[0]["media"][0]
    assert media_ref["kind"] == "table"
    assert media_ref["relation"] == "visible_from_child"
    assert media_ref["owner_level"] == "sub_question"
    assert media_ref["owner_label"] == "b"
    assert media_ref["page_number"] == 1
    assert media_ref["text_payload"] is not None


def test_cli_json_output_includes_enriched_media_metadata(
    monkeypatch,
    capsys,
) -> None:
    output = _run_cli(
        monkeypatch,
        capsys,
        MINERU_FIXTURES,
        "--year",
        "2018",
        "--paper",
        "8",
        "--question",
        "7",
        "--level",
        "question",
        "--format",
        "json",
    )

    payload = json.loads(output)

    assert len(payload) == 1
    media_ref = payload[0]["media"][0]
    assert media_ref["kind"] == "table"
    assert media_ref["relation"] == "visible_from_child"
    assert media_ref["owner_level"] == "sub_question"
    assert media_ref["owner_label"] == "b"
    assert media_ref["page_number"] == 1
    assert media_ref["text_payload"] is not None


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


def test_render_parser_text_full_includes_media_blocks() -> None:
    parsed_items = load_parsed_questions(MINERU_FIXTURES)
    filtered = filter_parsed_questions(
        parsed_items,
        source_pdf="y2018p8q7.pdf",
    )

    output = render_parser_text(filtered, view="full", max_text_chars=200)

    assert "media blocks:" in output
    assert "kind=table" in output
    assert "page_number=1" in output
    assert "bbox=(247.0, 472.0, 771.0, 545.0)" in output
    assert "order_index=2" in output
    assert "owner_hint_label=b" in output
    assert "is_shared_candidate=False" in output
    assert "text_payload=present" in output


def test_cli_parser_full_output_includes_media_blocks(
    monkeypatch,
    capsys,
) -> None:
    output = _run_cli(
        monkeypatch,
        capsys,
        MINERU_FIXTURES,
        "--stage",
        "parser",
        "--source-pdf",
        "y2018p1q4.pdf",
        "--view",
        "full",
    )

    assert "media blocks:" in output
    assert "kind=image" in output
    assert "page_number=1" in output
    assert "owner_hint_label=None" in output
    assert "is_shared_candidate=True" in output


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
