from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.chunking.cambridge_content_list_parser import CambridgeContentListParser
from src.chunking.models import Chunk, MediaRef, ParsedQuestion, make_chunk_id

logger = logging.getLogger(__name__)


def run_pipeline(
    mineru_output_dir: str,
    metadata_path: str | None = None,
    university: str = "cam",
) -> list[Chunk]:
    output_dir = Path(mineru_output_dir)
    metadata = _load_metadata(metadata_path) if metadata_path is not None else {}
    parser = CambridgeContentListParser()

    all_chunks: list[Chunk] = []
    parsed_count = 0
    warning_count = 0

    content_lists = sorted(output_dir.glob("**/*_content_list.json"))
    if not content_lists:
        logger.warning("No content_list.json files found in %s", output_dir)
        return []

    for cl_path in content_lists:
        # Derive PDF filename: y2025p1q1_content_list.json -> y2025p1q1.pdf
        stem = cl_path.stem.replace("_content_list", "")
        filename = f"{stem}.pdf"
        downloader_meta = metadata.get(filename, {})

        try:
            parsed_questions = parser.parse(str(cl_path))
        except Exception:
            logger.exception("Failed to process %s", cl_path.name)
            continue

        if not parsed_questions:
            logger.warning("No questions parsed from %s - skipping", cl_path.name)
            continue

        for pq in parsed_questions:
            chunks = _build_chunks(pq, downloader_meta, filename, university)
            _attach_media_refs(pq, chunks, cl_path.parent)
            all_chunks.extend(chunks)
            parsed_count += 1
            warning_count += len(pq.warnings)

    sub_count = sum(1 for c in all_chunks if c.chunk_level == "sub_question")
    q_count = sum(1 for c in all_chunks if c.chunk_level == "question")
    logger.info(
        "Pipeline complete: %d questions parsed, %d question chunks, "
        "%d sub-question chunks, %d warnings",
        parsed_count,
        q_count,
        sub_count,
        warning_count,
    )

    return all_chunks


def _load_metadata(metadata_path: str) -> dict[str, dict[str, Any]]:
    path = Path(metadata_path)
    if not path.exists():
        logger.warning("metadata.json not found at %s - proceeding without it", path)
        return {}

    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _build_chunks(
    parsed_question: ParsedQuestion,
    downloader_meta: dict[str, Any],
    filename: str,
    university: str,
) -> list[Chunk]:
    year = parsed_question.year or downloader_meta.get("year")
    paper = parsed_question.paper or downloader_meta.get("paper")
    question_number = parsed_question.question_number or downloader_meta.get("question")
    topic = downloader_meta.get("topic") or parsed_question.topic
    author = downloader_meta.get("author") or parsed_question.author

    question_text_parts = [parsed_question.preamble.strip()]
    if parsed_question.sub_questions:
        question_text_parts.extend(
            f"({sq.label}) {sq.text}" for sq in parsed_question.sub_questions
        )
    question_text = "\n\n".join(part for part in question_text_parts if part).strip()

    if year and paper and question_number:
        question_id = make_chunk_id(university, year, paper, question_number)
    else:
        question_id = f"{university}-{Path(filename).stem}"

    question_chunk = Chunk(
        id=question_id,
        chunk_level="question",
        parent_chunk_id=None,
        text=question_text,
        year=year,
        paper=paper,
        question_number=question_number,
        topic=topic,
        author=author,
        tripos_part=parsed_question.tripos_part,
        sub_question_label=None,
        marks=None,
        total_marks=parsed_question.total_marks,
        has_code=parsed_question.has_code,
        has_figure=parsed_question.has_figure,
        has_table=parsed_question.has_table,
        media=[],
        source_pdf=filename,
        warnings=list(parsed_question.warnings),
    )

    chunks = [question_chunk]

    for sq in parsed_question.sub_questions:
        if year and paper and question_number:
            sub_id = make_chunk_id(university, year, paper, question_number, sq.label)
        else:
            sub_id = f"{question_id}-{sq.label}"

        chunks.append(
            Chunk(
                id=sub_id,
                chunk_level="sub_question",
                parent_chunk_id=question_id,
                text=sq.text,
                year=year,
                paper=paper,
                question_number=question_number,
                topic=topic,
                author=author,
                tripos_part=parsed_question.tripos_part,
                sub_question_label=sq.label,
                marks=sq.marks,
                total_marks=parsed_question.total_marks,
                has_code=parsed_question.has_code,
                has_figure=parsed_question.has_figure,
                has_table=parsed_question.has_table,
                media=[],
                source_pdf=filename,
                warnings=[],
            )
        )

    return chunks


def _attach_media_refs(
    parsed_question: ParsedQuestion,
    chunks: list[Chunk],
    content_list_dir: Path,
) -> None:
    """Attach MediaRef entries from parser-preserved MinerU media blocks."""
    if not parsed_question.media_blocks:
        return

    question_chunk = next((c for c in chunks if c.chunk_level == "question"), None)
    if question_chunk is None:
        return

    sub_chunks_by_label = {
        chunk.sub_question_label: chunk
        for chunk in chunks
        if chunk.chunk_level == "sub_question" and chunk.sub_question_label is not None
    }

    for media_block in parsed_question.media_blocks:
        file_path = _resolve_media_path(media_block.file_path, content_list_dir)
        page_number = media_block.page_number
        bbox = media_block.bbox

        def attach_to_chunk(
            chunk: Chunk,
            relation: str,
            owner_level: str,
            owner_label: str | None,
        ) -> None:
            chunk.media.append(
                MediaRef(
                    media_id=media_block.media_id,
                    kind=media_block.kind,
                    file_path=file_path,
                    page_number=page_number,
                    bbox=bbox,
                    chunk_id=chunk.id,
                    relation=relation,
                    owner_level=owner_level,
                    owner_label=owner_label,
                    order_index=media_block.order_index,
                    text_payload=media_block.text_payload,
                    description=None,
                )
            )

        owner_chunk = (
            sub_chunks_by_label.get(media_block.owner_hint_label)
            if media_block.owner_hint_label is not None
            else None
        )

        # `is_shared_candidate` is parser-provided evidence that the media belongs
        # to the question preamble/shared context. It is not treated as a generic
        # ambiguity flag for "could belong anywhere".
        if media_block.is_shared_candidate:
            attach_to_chunk(
                question_chunk,
                relation="direct",
                owner_level="question",
                owner_label=None,
            )
            for sub_chunk in sub_chunks_by_label.values():
                attach_to_chunk(
                    sub_chunk,
                    relation="inherited_shared",
                    owner_level="question",
                    owner_label=None,
                )
            continue

        if owner_chunk is None:
            attach_to_chunk(
                question_chunk,
                relation="direct",
                owner_level="question",
                owner_label=None,
            )
            continue

        attach_to_chunk(
            owner_chunk,
            relation="direct",
            owner_level="sub_question",
            owner_label=media_block.owner_hint_label,
        )
        attach_to_chunk(
            question_chunk,
            relation="visible_from_child",
            owner_level="sub_question",
            owner_label=media_block.owner_hint_label,
        )


def _resolve_media_path(file_path: str | None, content_list_dir: Path) -> str | None:
    if file_path is None:
        return None

    path = Path(file_path)
    if not path.is_absolute():
        path = (content_list_dir / path).resolve()

    return str(path)
