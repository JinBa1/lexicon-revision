from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubQuestion:
    label: str  # e.g. "a", "b", "c"
    text: str
    marks: int | None = None


@dataclass
class MediaRef:
    file_path: str
    page_number: int  # 1-indexed
    bbox: tuple[float, float, float, float]  # (x0, y0, x1, y1) in points
    chunk_id: str
    description: str | None = None  # future: vision model description


@dataclass
class ParsedQuestion:
    tripos_part: str | None
    year: int | None
    paper: int | None
    question_number: int | None
    topic: str | None
    author: str | None
    preamble: str
    sub_questions: list[SubQuestion]
    total_marks: int | None
    has_code: bool
    has_figure: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    id: str
    chunk_level: str  # "question" or "sub_question"
    parent_chunk_id: str | None
    text: str

    # Metadata from downloader
    year: int | None
    paper: int | None
    question_number: int | None
    topic: str | None
    author: str | None

    # Metadata parsed from PDF
    tripos_part: str | None
    sub_question_label: str | None
    marks: int | None
    total_marks: int | None

    # Content flags
    has_code: bool
    has_figure: bool

    # Media & traceability
    media: list[MediaRef]
    source_pdf: str

    # Parse quality
    warnings: list[str] = field(default_factory=list)


def make_chunk_id(
    university: str,
    year: int,
    paper: int,
    question: int,
    sub_label: str | None = None,
) -> str:
    base = f"{university}-{year}-p{paper}-q{question}"
    if sub_label is not None:
        return f"{base}-{sub_label}"
    return base
