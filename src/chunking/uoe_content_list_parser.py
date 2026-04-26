from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any

from src.chunking.base_parser import BaseParser
from src.chunking.models import ParsedMediaBlock, ParsedQuestion, SubQuestion
from src.rendering.blocks import split_inline_math

# ---------------------------------------------------------------------------
# Cambridge-origin regex constants (kept as dead code — referenced nowhere in
# the UOE flow but harmless and avoids breaking any future cross-imports).
# ---------------------------------------------------------------------------

HEADER_RE = re.compile(
    r"COMPUTER SCIENCE TRIPOS\s+Part\s+([A-Z]+)\s*[–·\-]\s*(\d{4})\s*[–·\-]\s*"
    r"Paper\s+(\d+)"
)

QUESTION_LINE_RE = re.compile(
    r"^(?P<number>\d+)\s+(?P<topic>.+?)\s+\(\s*(?P<author>[A-Za-z0-9+]+)\s*\)\s*$"
)


def _sub_question_token_pattern(capture_label: bool) -> str:
    label = r"([a-z])" if capture_label else r"[a-z]"
    return rf"\(\s*{label}\s*\)"


SUB_QUESTION_RE = re.compile(rf"^{_sub_question_token_pattern(True)}\s+")
SUB_QUESTION_PREFIX_RE = re.compile(rf"^{_sub_question_token_pattern(False)}\s*")

MARKS_RE = re.compile(r"\[\s*(\d+)\s+marks?\s*\]")

# Block types to skip entirely
SKIP_TYPES = {"page_number"}
MINERU_BULLET_PREFIX_RE = re.compile(r"^\s*\s*")
NUMERIC_LIST_RE = re.compile(r"^\s*\d+\.\s+")
ROMAN_LABEL_RE = re.compile(r"^\s*\([ivxlcdm]+\)\s+", re.IGNORECASE)

# ---------------------------------------------------------------------------
# UOE-specific regex constants
# ---------------------------------------------------------------------------

UOE_COURSE_CODE_RE = re.compile(r"\b([A-Z]{3,4}\d{5})\b")
UOE_YEAR_RE = re.compile(r"\b(20\d{2})\b")
UOE_QUESTION_MARKER_RE = re.compile(r"^\s*Question\s+(\d+)\s*$")
UOE_COVER_BOILERPLATE_TOKENS = (
    "Date",
    "Time",
    "Duration",
    "Instructions",
    "Special Instructions",
    "Special Items Permitted",
    "Calculator",
    "Convener",
    "External Examiner",
)


@dataclass
class LogicalSegment:
    label: str | None
    blocks: list[dict[str, Any]]


class _TableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._current_row = []
        elif tag in {"td", "th"} and self._current_row is not None:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._current_cell is not None:
            if self._current_row is not None:
                self._current_row.append("".join(self._current_cell).strip())
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None


def _mineru_block_to_render_blocks(
    block: dict[str, Any], order_index: int = 0
) -> list[dict[str, Any]]:
    block_type = block.get("type")

    if block_type == "text":
        return _paragraph_blocks_from_text(block.get("text", ""))
    if block_type == "equation":
        latex = _strip_display_math_wrappers(block.get("text", "").strip())
        return [{"type": "equation", "latex": latex}] if latex else []
    if block_type == "list":
        return _list_blocks_from_items(block.get("list_items", []))
    if block_type == "code":
        return [
            {
                "type": "code",
                "code": block.get("code_body", ""),
                "language": None,
            }
        ]
    if block_type == "image":
        return [{"type": "image", "media_id": f"image_{order_index}"}]
    if block_type == "table":
        rows = _parse_table_rows(block.get("table_body", ""))
        if rows:
            return [
                {
                    "type": "table",
                    "rows": rows,
                    "media_id": f"table_{order_index}",
                }
            ]
        fallback_text = _malformed_table_fallback_text(block.get("table_body", ""))
        return _paragraph_blocks_from_text(fallback_text)

    text = block.get("text", "")
    if isinstance(text, str) and text.strip():
        return _paragraph_blocks_from_text(text)
    return []


def _paragraph_blocks_from_text(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if not stripped:
        return []
    return [
        {
            "type": "paragraph",
            "runs": [run.model_dump() for run in split_inline_math(stripped)],
        }
    ]


def _list_blocks_from_items(items: list[Any]) -> list[dict[str, Any]]:
    cleaned_items = [
        _strip_mineru_bullet_prefix(str(item).strip())
        for item in items
        if str(item).strip()
    ]
    if not cleaned_items:
        return []
    marker = _detect_list_marker(cleaned_items)
    rendered_items = (
        [_strip_numeric_list_prefix(item) for item in cleaned_items]
        if marker == "ordered"
        else cleaned_items
    )
    return [
        {
            "type": "list",
            "marker": marker,
            "items": [
                [run.model_dump() for run in split_inline_math(item)]
                for item in rendered_items
            ],
        }
    ]


def _strip_mineru_bullet_prefix(text: str) -> str:
    return MINERU_BULLET_PREFIX_RE.sub("", text, count=1)


def _detect_list_marker(items: list[str]) -> str:
    if all(NUMERIC_LIST_RE.match(item) for item in items):
        return "ordered"
    if any(ROMAN_LABEL_RE.match(item) for item in items):
        return "plain"
    return "bullet"


def _strip_numeric_list_prefix(text: str) -> str:
    return NUMERIC_LIST_RE.sub("", text, count=1)


def _strip_display_math_wrappers(text: str) -> str:
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        return text[2:-2].strip()
    return text


def _parse_table_rows(table_body: Any) -> list[list[str]]:
    if not isinstance(table_body, str):
        return []
    parser = _TableHTMLParser()
    parser.feed(table_body)
    parser.close()
    return parser.rows


def _malformed_table_fallback_text(table_body: Any) -> str:
    placeholder = "[table — see source]"
    if not isinstance(table_body, str):
        return placeholder
    raw_text = re.sub(r"<[^>]+>", " ", table_body)
    collapsed = " ".join(unescape(raw_text).split())
    if not collapsed:
        return placeholder
    return f"{placeholder} {collapsed}"


def _strip_label_from_render_blocks(blocks: list[dict[str, Any]]) -> None:
    for block in blocks:
        if block.get("type") == "paragraph":
            if _strip_label_from_runs(block.get("runs", [])):
                return
        elif block.get("type") == "list":
            for item in block.get("items", []):
                if _strip_label_from_runs(item):
                    return


def _strip_label_from_runs(runs: list[dict[str, Any]]) -> bool:
    for run in runs:
        if run.get("type") != "text":
            continue
        original = run.get("text", "")
        if not isinstance(original, str):
            continue
        stripped = SUB_QUESTION_PREFIX_RE.sub("", original, count=1)
        if stripped != original:
            run["text"] = stripped
            return True
    return False


def _insert_label_prefix(blocks: list[dict[str, Any]], label: str) -> None:
    prefix = f"({label}) "
    for block in blocks:
        if block.get("type") == "paragraph":
            if _insert_prefix_into_runs(block.get("runs", []), prefix):
                return
        elif block.get("type") == "list":
            for item in block.get("items", []):
                if _insert_prefix_into_runs(item, prefix):
                    return
    blocks.insert(0, {"type": "paragraph", "runs": [{"type": "text", "text": prefix}]})


def _insert_prefix_into_runs(runs: list[dict[str, Any]], prefix: str) -> bool:
    for run in runs:
        if run.get("type") == "text":
            run["text"] = f"{prefix}{run.get('text', '')}"
            return True
    if runs:
        runs.insert(0, {"type": "text", "text": prefix})
        return True
    return False


class UOEContentListParser(BaseParser):
    """Parser for MinerU content_list.json files (University of Edinburgh)."""

    def _mineru_block_to_render_blocks(
        self, block: dict[str, Any], order_index: int = 0
    ) -> list[dict[str, Any]]:
        return _mineru_block_to_render_blocks(block, order_index=order_index)

    def parse(self, content_list_path: str) -> list[ParsedQuestion]:
        with open(content_list_path, encoding="utf-8") as f:
            blocks: list[dict] = json.load(f)

        warnings: list[str] = []

        # Filter out skip types
        blocks = [b for b in blocks if b.get("type") not in SKIP_TYPES]

        # Extract cover metadata and locate first Question N block
        cover_meta, first_q_idx = self._extract_cover_metadata(blocks)

        # Build warnings for missing cover fields
        if not cover_meta.get("course_code"):
            warnings.append("uoe_course_code_missing")
        if not cover_meta.get("course_title"):
            warnings.append("uoe_course_title_missing")
        if not cover_meta.get("year"):
            warnings.append("uoe_year_missing")

        # Slice post-cover blocks (body)
        post_cover_blocks = blocks[first_q_idx:]
        has_code, has_figure, has_table = self._detect_content_flags(blocks)
        media_blocks = self._extract_media_blocks(post_cover_blocks)
        preamble, sub_questions = self._split_sub_questions(post_cover_blocks)

        return [
            ParsedQuestion(
                tripos_part=cover_meta.get("course_code"),
                year=cover_meta.get("year"),
                paper=None,
                question_number=None,
                topic=cover_meta.get("course_title"),
                author=None,
                preamble=preamble,
                sub_questions=sub_questions,
                total_marks=self._compute_total_marks(sub_questions),
                has_code=has_code,
                has_figure=has_figure,
                has_table=has_table,
                media_blocks=media_blocks,
                warnings=warnings,
            )
        ]

    def parse_with_segments(
        self, content_list_path: str
    ) -> tuple[list[ParsedQuestion], list[list[LogicalSegment]]]:
        parsed_questions = self.parse(content_list_path)

        with open(content_list_path, encoding="utf-8") as f:
            blocks: list[dict[str, Any]] = json.load(f)

        blocks = [b for b in blocks if b.get("type") not in SKIP_TYPES]
        _, first_q_idx = self._extract_cover_metadata(blocks)
        post_cover_blocks = blocks[first_q_idx:]

        return parsed_questions, [self._split_into_logical_segments(post_cover_blocks)]

    def _extract_cover_metadata(self, content_blocks: list[dict]) -> tuple[dict, int]:
        """Walk blocks until first 'Question 1' marker.

        Returns (metadata_dict, first_question_index).
        metadata_dict keys: course_code, course_title, year.
        If no Question 1 found, first_question_index == len(content_blocks).
        """
        course_code: str | None = None
        course_title: str | None = None
        year: int | None = None

        boilerplate_lower = tuple(t.lower() for t in UOE_COVER_BOILERPLATE_TOKENS)

        for i, block in enumerate(content_blocks):
            text_raw = block.get("text", "") or ""
            text = text_raw.strip()

            # Check for Question N marker — stop here
            if UOE_QUESTION_MARKER_RE.match(text):
                break

            block_type = block.get("type")
            # Only scan text blocks for metadata
            if block_type != "text":
                continue

            # Course code: MECE10017 style
            if course_code is None:
                cm = UOE_COURSE_CODE_RE.search(text)
                if cm:
                    course_code = cm.group(1)

            # Year: first 4-digit year 20xx
            if year is None:
                ym = UOE_YEAR_RE.search(text)
                if ym:
                    year = int(ym.group(1))

            # Course title: non-boilerplate, meaningful length
            if course_title is None and text:
                text_lower = text.lower()
                is_boilerplate = any(
                    text_lower.startswith(token) for token in boilerplate_lower
                )
                is_code_line = bool(UOE_COURSE_CODE_RE.fullmatch(text.replace(" ", "")))
                looks_like_title = (
                    not is_boilerplate
                    and not is_code_line
                    and len(text) >= 10
                    and len(text) <= 160
                    and not re.fullmatch(r"[\d/:\- ]+", text)
                    and text
                    not in ("SCHOOL OF ENGINEERING", "THE UNIVERSITY of EDINBURGH")
                )
                if looks_like_title:
                    words = text.split()
                    if len(words) >= 3:
                        course_title = text
        else:
            # No Question N found
            return {
                "course_code": course_code,
                "course_title": course_title,
                "year": year,
            }, len(content_blocks)

        return {
            "course_code": course_code,
            "course_title": course_title,
            "year": year,
        }, i

    def _detect_content_flags(self, blocks: list[dict]) -> tuple[bool, bool, bool]:
        """Detect has_code, has_figure, has_table from block types."""
        has_code = False
        has_figure = False
        has_table = False
        for block in blocks:
            block_type = block.get("type")
            if block_type == "code":
                has_code = True
            elif block_type == "image":
                has_figure = True
            elif block_type == "table":
                has_table = True
        return has_code, has_figure, has_table

    def _extract_block_text(self, block: dict) -> str:
        """Extract text content from a block."""
        block_type = block.get("type")
        if block_type == "code":
            return block.get("code_body", "").strip()
        elif block_type == "equation":
            return block.get("text", "").strip()
        elif block_type == "table":
            return block.get("table_body", "").strip()
        elif block_type == "image":
            return ""
        elif block_type == "list":
            items = block.get("list_items", [])
            return "\n".join(item.strip() for item in items)
        else:
            return block.get("text", "").strip()

    def _split_sub_questions(
        self, body_blocks: list[dict]
    ) -> tuple[str, list[SubQuestion]]:
        """Split body into preamble and sub-questions (Cambridge logic)."""
        segments = self._flatten_to_segments(body_blocks)

        if not segments:
            return "", []

        candidates: list[tuple[int, str]] = []
        for i, (text, label) in enumerate(segments):
            if label is not None:
                candidates.append((i, label))

        sub_starts = self._filter_sequential_labels(candidates)

        if not sub_starts:
            all_text = "\n".join(text for text, _ in segments).strip()
            return all_text, []

        preamble_parts = [text for text, _ in segments[: sub_starts[0][0]]]
        preamble = "\n".join(preamble_parts).strip()

        sub_questions: list[SubQuestion] = []
        for idx, (start_seg, label) in enumerate(sub_starts):
            if idx + 1 < len(sub_starts):
                end_seg = sub_starts[idx + 1][0]
            else:
                end_seg = len(segments)

            sub_parts = [text for text, _ in segments[start_seg:end_seg]]
            sub_text = "\n".join(sub_parts).strip()

            sub_text = self._strip_top_level_label_prefix(sub_text)

            marks = self._extract_marks(sub_text)
            cleaned_text = MARKS_RE.sub("", sub_text).strip()

            sub_questions.append(
                SubQuestion(label=label, text=cleaned_text, marks=marks)
            )

        return preamble, sub_questions

    def _extract_media_blocks(self, body_blocks: list[dict]) -> list[ParsedMediaBlock]:
        """Preserve media/table block facts for later ownership assignment."""
        owner_hints_by_block = self._compute_owner_hints_by_block(body_blocks)
        media_blocks: list[ParsedMediaBlock] = []

        for order_index, block in enumerate(body_blocks):
            block_type = block.get("type")
            if block_type not in {"image", "table"}:
                continue

            page_idx = block.get("page_idx")
            bbox = block.get("bbox")
            owner_hint_label = owner_hints_by_block.get(order_index)
            media_blocks.append(
                ParsedMediaBlock(
                    media_id=f"{block_type}_{order_index}",
                    kind=block_type,
                    file_path=block.get("img_path"),
                    page_number=page_idx + 1 if isinstance(page_idx, int) else None,
                    bbox=self._normalize_bbox(bbox),
                    order_index=order_index,
                    text_payload=self._extract_media_text_payload(block),
                    owner_hint_label=owner_hint_label,
                    is_shared_candidate=owner_hint_label is None,
                )
            )

        return media_blocks

    def _flatten_to_segments(
        self, body_blocks: list[dict]
    ) -> list[tuple[str, str | None]]:
        """Flatten blocks into (text, top_level_label_or_None) segments."""
        segments: list[tuple[str, str | None]] = []

        for block in body_blocks:
            block_type = block.get("type")

            if block_type == "list":
                items = block.get("list_items", [])
                for item in items:
                    item_text = item.strip()
                    label = self._detect_top_level_label(item_text)
                    segments.append((item_text, label))

            elif block_type in ("text", "equation", "code", "table", "image"):
                text = self._extract_block_text(block)
                if not text:
                    continue
                label = self._detect_top_level_label(text)
                segments.append((text, label))

        return segments

    def _compute_owner_hints_by_block(self, body_blocks: list[dict]) -> dict[int, str]:
        """Map each block index to the latest top-level label seen by segment order."""
        segments = self._flatten_to_positioned_segments(body_blocks)
        candidates = [
            (segment_index, label)
            for segment_index, (_, label, _) in enumerate(segments)
            if label is not None
        ]
        top_level_starts = self._filter_sequential_labels(candidates)
        labels_by_segment = {
            segment_index: label for segment_index, label in top_level_starts
        }

        owner_hints_by_block: dict[int, str] = {}
        current_owner_label: str | None = None
        segments_by_block: dict[int, list[int]] = {}

        for segment_index, (_, _, block_index) in enumerate(segments):
            segments_by_block.setdefault(block_index, []).append(segment_index)

        for block_index, _ in enumerate(body_blocks):
            for segment_index in segments_by_block.get(block_index, []):
                current_owner_label = labels_by_segment.get(
                    segment_index, current_owner_label
                )
            if current_owner_label is not None:
                owner_hints_by_block[block_index] = current_owner_label

        return owner_hints_by_block

    def _flatten_to_positioned_segments(
        self, body_blocks: list[dict]
    ) -> list[tuple[str, str | None, int]]:
        """Flatten blocks into segments while retaining source body-block index."""
        segments: list[tuple[str, str | None, int]] = []

        for block_index, block in enumerate(body_blocks):
            block_type = block.get("type")

            if block_type == "list":
                items = block.get("list_items", [])
                for item in items:
                    item_text = item.strip()
                    label = self._detect_top_level_label(item_text)
                    segments.append((item_text, label, block_index))

            elif block_type in ("text", "equation", "code", "table", "image"):
                text = self._extract_block_text(block)
                if not text:
                    continue
                label = self._detect_top_level_label(text)
                segments.append((text, label, block_index))

        return segments

    def _split_into_logical_segments(
        self, body_blocks: list[dict[str, Any]]
    ) -> list[LogicalSegment]:
        positioned_segments = self._flatten_to_positioned_segments(body_blocks)
        candidates = [
            (segment_index, label)
            for segment_index, (_, label, _) in enumerate(positioned_segments)
            if label is not None
        ]
        top_level_starts = self._filter_sequential_labels(candidates)
        labels_by_segment = {
            segment_index: label for segment_index, label in top_level_starts
        }
        segment_indices_by_list_item: dict[tuple[int, int], int] = {}
        segment_indices_by_block: dict[int, int] = {}

        segment_index = 0
        for block_index, block in enumerate(body_blocks):
            block_type = block.get("type")
            if block_type == "list":
                for item_index, item in enumerate(block.get("list_items", [])):
                    if str(item).strip():
                        segment_indices_by_list_item[(block_index, item_index)] = (
                            segment_index
                        )
                        segment_index += 1
            elif block_type in ("text", "equation", "code", "table", "image"):
                if self._extract_block_text(block):
                    segment_indices_by_block[block_index] = segment_index
                    segment_index += 1

        segments: list[LogicalSegment] = []
        current_segment: LogicalSegment | None = None

        def ensure_segment(label: str | None) -> LogicalSegment:
            nonlocal current_segment
            if current_segment is None:
                current_segment = LogicalSegment(label=label, blocks=[])
                segments.append(current_segment)
            return current_segment

        def start_segment(label: str) -> LogicalSegment:
            nonlocal current_segment
            current_segment = LogicalSegment(label=label, blocks=[])
            segments.append(current_segment)
            return current_segment

        for block_index, block in enumerate(body_blocks):
            block_type = block.get("type")
            if block_type == "list":
                current_items: list[str] = []
                item_owner: LogicalSegment | None = None

                def flush_items() -> None:
                    nonlocal current_items, item_owner
                    if current_items and item_owner is not None:
                        item_owner.blocks.extend(_list_blocks_from_items(current_items))
                    current_items = []
                    item_owner = None

                for item_index, item in enumerate(block.get("list_items", [])):
                    item_text = str(item).strip()
                    if not item_text:
                        continue
                    item_segment_index = segment_indices_by_list_item[
                        (block_index, item_index)
                    ]
                    label = labels_by_segment.get(item_segment_index)
                    if label is not None:
                        flush_items()
                        owner = start_segment(label)
                    else:
                        owner = ensure_segment(None)

                    if item_owner is not owner:
                        flush_items()
                        item_owner = owner
                    current_items.append(item_text)

                flush_items()
                continue

            block_segment_index = segment_indices_by_block.get(block_index)
            if block_segment_index is not None:
                label = labels_by_segment.get(block_segment_index)
                owner = (
                    start_segment(label) if label is not None else ensure_segment(None)
                )
            else:
                owner = ensure_segment(None)

            owner.blocks.extend(
                self._mineru_block_to_render_blocks(block, order_index=block_index)
            )

        for segment in segments:
            if segment.label is not None:
                _strip_label_from_render_blocks(segment.blocks)

        return [
            segment
            for segment in segments
            if segment.blocks or segment.label is not None
        ]

    def _extract_media_text_payload(self, block: dict) -> str | None:
        if block.get("type") == "table":
            payload = block.get("table_body", "").strip()
            return payload or None
        return None

    def _normalize_bbox(
        self, bbox: list[float] | tuple[float, ...] | None
    ) -> tuple[float, float, float, float] | None:
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            return None
        return tuple(float(value) for value in bbox)

    def _filter_sequential_labels(
        self, candidates: list[tuple[int, str]]
    ) -> list[tuple[int, str]]:
        """Filter candidates to only include sequentially ordered labels."""
        if not candidates:
            return []

        result: list[tuple[int, str]] = []
        expected_ord = ord("a")

        for seg_idx, label in candidates:
            if ord(label) == expected_ord:
                result.append((seg_idx, label))
                expected_ord += 1

        return result

    def _detect_top_level_label(self, text: str) -> str | None:
        """Detect a single-letter sub-question token at the start of text."""
        match = SUB_QUESTION_RE.match(text)
        if match:
            return match.group(1)
        return None

    def _strip_top_level_label_prefix(self, text: str) -> str:
        """Remove a leading top-level label token while preserving body text."""
        return SUB_QUESTION_PREFIX_RE.sub("", text, count=1)

    def _extract_marks(self, text: str) -> int | None:
        """Extract total marks from text. Uses the last [N marks] found."""
        matches = MARKS_RE.findall(text)
        if not matches:
            return None
        return sum(int(m) for m in matches)

    def _compute_total_marks(self, sub_questions: list[SubQuestion]) -> int | None:
        if not sub_questions:
            return None
        marks = [sq.marks for sq in sub_questions]
        if any(m is None for m in marks):
            return None
        return sum(m for m in marks if m is not None)
