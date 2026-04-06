from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import fitz
from src.chunking.cambridge_parser import CambridgeParser
from src.chunking.models import Chunk, MediaRef, ParsedQuestion, make_chunk_id

logger = logging.getLogger(__name__)


def run_pipeline(
    pdf_dir: str,
    metadata_path: str,
    university: str = "cam",
    media_dir: str | None = None,
) -> list[Chunk]:
    pdf_dir_path = Path(pdf_dir)
    media_dir_path = _resolve_media_dir(pdf_dir_path, media_dir)
    metadata = _load_metadata(metadata_path)
    parser = CambridgeParser()

    all_chunks: list[Chunk] = []
    parsed_count = 0
    warning_count = 0

    pdf_files = sorted(pdf_dir_path.glob("**/*.pdf"))
    if not pdf_files:
        logger.warning("No PDF files found in %s", pdf_dir)
        return []

    for pdf_path in pdf_files:
        filename = pdf_path.name
        downloader_meta = metadata.get(filename, {})

        try:
            parsed_questions = parser.parse(str(pdf_path))
        except Exception:
            logger.exception("Failed to process %s", filename)
            continue

        if not parsed_questions:
            logger.warning("No text extracted from %s - skipping", filename)
            continue

        for parsed_question in parsed_questions:
            chunks = _build_chunks(
                parsed_question, downloader_meta, filename, university
            )
            if any(chunk.has_figure for chunk in chunks):
                _extract_and_save_media(str(pdf_path), chunks, media_dir_path)
            all_chunks.extend(chunks)
            parsed_count += 1
            warning_count += len(parsed_question.warnings)

    sub_count = sum(1 for chunk in all_chunks if chunk.chunk_level == "sub_question")
    q_count = sum(1 for chunk in all_chunks if chunk.chunk_level == "question")
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
            f"({sub_question.label}) {sub_question.text}"
            for sub_question in parsed_question.sub_questions
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

    for sub_question in parsed_question.sub_questions:
        if year and paper and question_number:
            sub_question_id = make_chunk_id(
                university, year, paper, question_number, sub_question.label
            )
        else:
            sub_question_id = f"{question_id}-{sub_question.label}"

        chunks.append(
            Chunk(
                id=sub_question_id,
                chunk_level="sub_question",
                parent_chunk_id=question_id,
                text=sub_question.text,
                year=year,
                paper=paper,
                question_number=question_number,
                topic=topic,
                author=author,
                tripos_part=parsed_question.tripos_part,
                sub_question_label=sub_question.label,
                marks=sub_question.marks,
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


def _resolve_media_dir(pdf_dir: Path, media_dir: str | None) -> Path:
    if media_dir is not None:
        return Path(media_dir)
    return pdf_dir.parent / "media"


def _extract_and_save_media(
    pdf_path: str, chunks: list[Chunk], media_dir: Path
) -> None:
    """Extract images from a PDF and attach them to the nearest chunk."""
    document = fitz.open(pdf_path)

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            image_list = page.get_images(full=True)
            if not image_list:
                continue

            text_dict = page.get_text("dict")
            sub_question_positions = _get_sub_question_positions(text_dict)

            for image_index, image_info in enumerate(image_list):
                xref = image_info[0]
                image_rects = page.get_image_rects(xref)
                if not image_rects:
                    continue

                bbox = image_rects[0]
                bbox_tuple = (
                    float(bbox.x0),
                    float(bbox.y0),
                    float(bbox.x1),
                    float(bbox.y1),
                )
                target_chunk = _assign_image_to_chunk(
                    chunks, bbox_tuple, sub_question_positions, page_number
                )

                chunk_media_dir = media_dir / target_chunk.id
                chunk_media_dir.mkdir(parents=True, exist_ok=True)
                image_path = chunk_media_dir / f"figure_{image_index + 1}.png"

                pixmap = fitz.Pixmap(document, xref)
                if pixmap.n > 4:
                    pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
                pixmap.save(str(image_path))

                target_chunk.media.append(
                    MediaRef(
                        file_path=str(image_path),
                        page_number=page_number,
                        bbox=bbox_tuple,
                        chunk_id=target_chunk.id,
                        description=None,
                    )
                )
    finally:
        document.close()


def _get_sub_question_positions(text_dict: dict[str, Any]) -> list[tuple[str, float]]:
    """Extract y-positions of top-level sub-question labels from page text."""
    positions: list[tuple[str, float]] = []

    for block in text_dict.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for line in block.get("lines", []):
            line_text = "".join(span.get("text", "") for span in line.get("spans", []))
            if (
                len(line_text) >= 3
                and line_text.startswith("(")
                and line_text[2:3] == ")"
            ):
                label = line_text[1:2]
                if label.isalpha() and label != "i":
                    positions.append((label, float(line["bbox"][1])))

    return positions


def _assign_image_to_chunk(
    chunks: list[Chunk],
    bbox: tuple[float, float, float, float],
    sub_question_positions: list[tuple[str, float]],
    page_number: int,
) -> Chunk:
    """Assign an image to the closest applicable chunk on the same page."""
    del page_number

    image_y = bbox[1]
    assigned_label: str | None = None
    for label, y_position in reversed(sub_question_positions):
        if image_y >= y_position:
            assigned_label = label
            break

    if assigned_label is not None:
        for chunk in chunks:
            if chunk.sub_question_label == assigned_label:
                return chunk

    for chunk in chunks:
        if chunk.chunk_level == "question":
            return chunk

    return chunks[0]
