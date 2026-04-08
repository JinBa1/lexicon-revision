"""Inspect parser-stage or pipeline-stage output from MinerU conversions.

Usage:
    python scripts/inspect_pipeline.py \
        tests/data/mineru_fixtures data/papers/metadata.json
    python scripts/inspect_pipeline.py \
        tests/data/mineru_fixtures data/papers/metadata.json \
        --stage parser --source-pdf y2018p5q7.pdf --view full
    python scripts/inspect_pipeline.py \
        data/mineru_output data/papers/metadata.json \
        --year 2025 --paper 1 --question 7
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

# Allow direct execution via `python scripts/inspect_pipeline.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.chunking.cambridge_content_list_parser import (  # noqa: E402
    CambridgeContentListParser,
)
from src.chunking.models import (  # noqa: E402
    Chunk,
    MediaRef,
    ParsedMediaBlock,
    ParsedQuestion,
)
from src.chunking.pipeline import run_pipeline  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect parser or pipeline output",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python scripts/inspect_pipeline.py "
            "tests/data/mineru_fixtures data/papers/metadata.json\n"
            "  python scripts/inspect_pipeline.py "
            "tests/data/mineru_fixtures data/papers/metadata.json "
            "--stage parser --source-pdf y2018p5q7.pdf --view full\n"
            "  python scripts/inspect_pipeline.py "
            "data/mineru_output data/papers/metadata.json "
            "--year 2025 --paper 1 --question 7\n"
        ),
    )
    parser.add_argument("mineru_output_dir", help="Directory containing MinerU output")
    parser.add_argument(
        "metadata_path",
        nargs="?",
        default=None,
        help="Path to metadata.json (optional)",
    )
    parser.add_argument("--university", default="cam", help="University code")
    parser.add_argument(
        "--stage",
        choices=["pipeline", "parser"],
        default="pipeline",
        help="Inspect final chunks or intermediate ParsedQuestion output",
    )
    parser.add_argument("--year", type=int, help="Filter by year")
    parser.add_argument("--paper", type=int, help="Filter by paper number")
    parser.add_argument("--question", type=int, help="Filter by question number")
    parser.add_argument("--source-pdf", help="Filter by source PDF filename")
    parser.add_argument("--chunk-id", help="Filter by exact chunk ID")
    parser.add_argument(
        "--level",
        choices=["question", "sub_question"],
        help="Filter by chunk level (pipeline stage only)",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--view",
        choices=["summary", "full"],
        default="summary",
        help="Detail level",
    )
    parser.add_argument(
        "--max-text-chars",
        type=int,
        default=200,
        help="Text preview length for summary view",
    )
    return parser.parse_args()


def _truncate_text(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return f"{compact[: max_chars - 3]}..."


def _derive_source_pdf(content_list_path: Path) -> str:
    stem = content_list_path.stem.replace("_content_list", "")
    return f"{stem}.pdf"


def filter_chunks(
    chunks: list[Chunk],
    *,
    year: int | None = None,
    paper: int | None = None,
    question: int | None = None,
    source_pdf: str | None = None,
    chunk_id: str | None = None,
    level: str | None = None,
) -> list[Chunk]:
    filtered = chunks

    if year is not None:
        filtered = [chunk for chunk in filtered if chunk.year == year]
    if paper is not None:
        filtered = [chunk for chunk in filtered if chunk.paper == paper]
    if question is not None:
        filtered = [chunk for chunk in filtered if chunk.question_number == question]
    if source_pdf is not None:
        filtered = [chunk for chunk in filtered if chunk.source_pdf == source_pdf]
    if chunk_id is not None:
        filtered = [chunk for chunk in filtered if chunk.id == chunk_id]
    if level is not None:
        filtered = [chunk for chunk in filtered if chunk.chunk_level == level]

    return filtered


def load_parsed_questions(mineru_output_dir: str) -> list[dict[str, Any]]:
    output_dir = Path(mineru_output_dir)
    parser = CambridgeContentListParser()
    parsed_items: list[dict[str, Any]] = []

    content_lists = sorted(output_dir.glob("**/*_content_list.json"))
    content_lists = [
        path for path in content_lists if not path.name.endswith("_v2.json")
    ]

    for content_list_path in content_lists:
        parsed_questions = parser.parse(str(content_list_path))
        for parsed_question in parsed_questions:
            parsed_items.append(
                {
                    "content_list_path": str(content_list_path),
                    "source_pdf": _derive_source_pdf(content_list_path),
                    "parsed_question": parsed_question,
                }
            )

    return parsed_items


def filter_parsed_questions(
    parsed_items: list[dict[str, Any]],
    *,
    year: int | None = None,
    paper: int | None = None,
    question: int | None = None,
    source_pdf: str | None = None,
) -> list[dict[str, Any]]:
    filtered = parsed_items

    if year is not None:
        filtered = [item for item in filtered if item["parsed_question"].year == year]
    if paper is not None:
        filtered = [item for item in filtered if item["parsed_question"].paper == paper]
    if question is not None:
        filtered = [
            item
            for item in filtered
            if item["parsed_question"].question_number == question
        ]
    if source_pdf is not None:
        filtered = [item for item in filtered if item["source_pdf"] == source_pdf]

    return filtered


def serialize_chunk(chunk: Chunk) -> dict[str, Any]:
    return asdict(chunk)


def serialize_parsed_question(parsed_question: ParsedQuestion) -> dict[str, Any]:
    return asdict(parsed_question)


def render_json(items: list[Any]) -> str:
    if not items:
        return "[]"
    if isinstance(items[0], Chunk):
        payload = [serialize_chunk(item) for item in items]
    else:
        payload = [serialize_parsed_question(item) for item in items]
    return json.dumps(payload, indent=2)


def render_text(chunks: list[Chunk], *, view: str, max_text_chars: int) -> str:
    if not chunks:
        return "No chunks matched the requested filters."

    lines = [f"Matched {len(chunks)} chunk(s)."]

    for chunk in chunks:
        lines.append("")
        lines.append(f"{chunk.id} [{chunk.chunk_level}]")
        lines.append(f"source: {chunk.source_pdf}")
        lines.append(
            "metadata: "
            f"year={chunk.year} paper={chunk.paper} question={chunk.question_number} "
            f"sub={chunk.sub_question_label} topic={chunk.topic!r} "
            f"author={chunk.author!r}"
        )
        lines.append(
            "flags: "
            f"code={chunk.has_code} figure={chunk.has_figure} table={chunk.has_table} "
            f"media={len(chunk.media)} warnings={len(chunk.warnings)}"
        )
        if chunk.parent_chunk_id is not None:
            lines.append(f"parent: {chunk.parent_chunk_id}")
        if chunk.marks is not None or chunk.total_marks is not None:
            lines.append(f"marks: part={chunk.marks} total={chunk.total_marks}")
        if chunk.warnings:
            lines.append(f"warnings: {', '.join(chunk.warnings)}")

        if view == "summary":
            lines.append(f"text: {_truncate_text(chunk.text, max_text_chars)}")
            continue

        lines.append("text:")
        lines.append(chunk.text)
        if chunk.media:
            lines.append("media:")
            for media in chunk.media:
                lines.extend(_render_media_ref(media))

    return "\n".join(lines)


def _format_media_file_path(file_path: str | None) -> str:
    if file_path is None:
        return "None"

    path = Path(file_path)
    if path.is_absolute():
        try:
            return str(path.relative_to(REPO_ROOT))
        except ValueError:
            return str(path)

    return str(path)


def _render_media_ref(media: MediaRef) -> list[str]:
    lines = [
        (
            "- "
            f"media_id={media.media_id} kind={media.kind} relation={media.relation} "
            f"owner_level={media.owner_level} owner_label={media.owner_label} "
            f"page_number={media.page_number} order_index={media.order_index} "
            f"bbox={media.bbox} "
            f"file_path={_format_media_file_path(media.file_path)}"
        )
    ]

    if media.kind == "table" or media.text_payload is not None:
        if media.text_payload is None:
            lines.append("  text_payload=absent")
        else:
            preview = _truncate_text(media.text_payload, 80)
            lines.append(
                "  "
                f"text_payload=present text_payload_len={len(media.text_payload)} "
                f"preview={preview!r}"
            )

    return lines


def _render_parsed_media_block(media: ParsedMediaBlock) -> list[str]:
    lines = [
        (
            "- "
            f"media_id={media.media_id} kind={media.kind} "
            f"page_number={media.page_number} order_index={media.order_index} "
            f"bbox={media.bbox} "
            f"owner_hint_label={media.owner_hint_label} "
            f"is_shared_candidate={media.is_shared_candidate} "
            f"file_path={_format_media_file_path(media.file_path)}"
        )
    ]

    if media.kind == "table" or media.text_payload is not None:
        if media.text_payload is None:
            lines.append("  text_payload=absent")
        else:
            preview = _truncate_text(media.text_payload, 80)
            lines.append(
                "  "
                f"text_payload=present text_payload_len={len(media.text_payload)} "
                f"preview={preview!r}"
            )

    return lines


def render_parser_text(
    parsed_items: list[dict[str, Any]],
    *,
    view: str,
    max_text_chars: int,
) -> str:
    if not parsed_items:
        return "No parsed questions matched the requested filters."

    lines = [f"Matched {len(parsed_items)} parsed question(s)."]

    for item in parsed_items:
        parsed_question: ParsedQuestion = item["parsed_question"]
        lines.append("")
        lines.append(item["source_pdf"])
        lines.append(f"content_list: {item['content_list_path']}")
        lines.append(
            "metadata: "
            f"tripos={parsed_question.tripos_part!r} year={parsed_question.year} "
            f"paper={parsed_question.paper} question={parsed_question.question_number} "
            f"topic={parsed_question.topic!r} author={parsed_question.author!r}"
        )
        lines.append(
            "flags: "
            f"code={parsed_question.has_code} figure={parsed_question.has_figure} "
            f"table={parsed_question.has_table} "
            f"total_marks={parsed_question.total_marks}"
        )
        lines.append(
            f"sub_questions: {len(parsed_question.sub_questions)} "
            f"warnings={len(parsed_question.warnings)}"
        )
        if parsed_question.warnings:
            lines.append(f"warnings: {', '.join(parsed_question.warnings)}")

        if view == "summary":
            lines.append(
                f"preamble: {_truncate_text(parsed_question.preamble, max_text_chars)}"
            )
            labels = [
                sub_question.label for sub_question in parsed_question.sub_questions
            ]
            lines.append(f"labels: {labels}")
            continue

        lines.append("preamble:")
        lines.append(parsed_question.preamble)
        if parsed_question.media_blocks:
            lines.append("media blocks:")
            for media_block in parsed_question.media_blocks:
                lines.extend(_render_parsed_media_block(media_block))
        if parsed_question.sub_questions:
            lines.append("sub-question details:")
            for sub_question in parsed_question.sub_questions:
                lines.append(f"- ({sub_question.label}) marks={sub_question.marks}")
                lines.append(sub_question.text)

    return "\n".join(lines)


def _render_pipeline(args: argparse.Namespace) -> str:
    chunks = run_pipeline(
        mineru_output_dir=args.mineru_output_dir,
        metadata_path=args.metadata_path,
        university=args.university,
    )
    filtered = filter_chunks(
        chunks,
        year=args.year,
        paper=args.paper,
        question=args.question,
        source_pdf=args.source_pdf,
        chunk_id=args.chunk_id,
        level=args.level,
    )

    if args.output_format == "json":
        return render_json(filtered)
    return render_text(
        filtered,
        view=args.view,
        max_text_chars=args.max_text_chars,
    )


def _render_parser(args: argparse.Namespace) -> str:
    parsed_items = load_parsed_questions(args.mineru_output_dir)
    filtered = filter_parsed_questions(
        parsed_items,
        year=args.year,
        paper=args.paper,
        question=args.question,
        source_pdf=args.source_pdf,
    )

    if args.output_format == "json":
        return render_json([item["parsed_question"] for item in filtered])
    return render_parser_text(
        filtered,
        view=args.view,
        max_text_chars=args.max_text_chars,
    )


def main() -> None:
    args = parse_args()

    if args.stage == "parser":
        print(_render_parser(args))
    else:
        print(_render_pipeline(args))


if __name__ == "__main__":
    main()
