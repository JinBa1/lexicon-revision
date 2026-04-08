from __future__ import annotations

import json
import re

from src.chunking.base_parser import BaseParser
from src.chunking.models import ParsedQuestion, SubQuestion

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


class CambridgeContentListParser(BaseParser):
    """Parser for MinerU content_list.json files (Cambridge CS Tripos)."""

    def parse(self, content_list_path: str) -> list[ParsedQuestion]:
        with open(content_list_path, encoding="utf-8") as f:
            blocks: list[dict] = json.load(f)

        warnings: list[str] = []

        # Filter out skip types
        blocks = [b for b in blocks if b.get("type") not in SKIP_TYPES]

        header = self._parse_header(blocks)
        question_info = self._parse_question_line(blocks)
        has_code, has_figure, has_table = self._detect_content_flags(blocks)

        if header is None:
            warnings.append("header_parse_failed")
        if question_info is None:
            warnings.append("question_line_parse_failed")

        # Find body blocks (everything after the question line, excluding header)
        body_blocks = self._extract_body_blocks(blocks, question_info)
        preamble, sub_questions = self._split_sub_questions(body_blocks)

        return [
            ParsedQuestion(
                tripos_part=header["tripos_part"] if header else None,
                year=header["year"] if header else None,
                paper=header["paper"] if header else None,
                question_number=(
                    question_info["question_number"] if question_info else None
                ),
                topic=question_info["topic"] if question_info else None,
                author=question_info["author"] if question_info else None,
                preamble=preamble,
                sub_questions=sub_questions,
                total_marks=self._compute_total_marks(sub_questions),
                has_code=has_code,
                has_figure=has_figure,
                has_table=has_table,
                warnings=warnings,
            )
        ]

    def _parse_header(self, blocks: list[dict]) -> dict[str, str | int] | None:
        """Find and parse the header block (usually at the end)."""
        for block in blocks:
            if block.get("type") == "header":
                text = block.get("text", "").strip()
                match = HEADER_RE.search(text)
                if match:
                    return {
                        "tripos_part": f"Part {match.group(1)}",
                        "year": int(match.group(2)),
                        "paper": int(match.group(3)),
                    }
        # Fallback: search all text blocks too
        for block in blocks:
            text = block.get("text", "").strip()
            match = HEADER_RE.search(text)
            if match:
                return {
                    "tripos_part": f"Part {match.group(1)}",
                    "year": int(match.group(2)),
                    "paper": int(match.group(3)),
                }
        return None

    def _parse_question_line(self, blocks: list[dict]) -> dict[str, str | int] | None:
        """Find the question line: 'N Topic (author)'."""
        for i, block in enumerate(blocks):
            if block.get("type") not in ("text",):
                continue
            text = block.get("text", "").strip()
            match = QUESTION_LINE_RE.match(text)
            if match:
                return {
                    "question_number": int(match.group("number")),
                    "topic": match.group("topic").strip(),
                    "author": match.group("author"),
                    "block_index": i,
                }
        return None

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

    def _extract_body_blocks(
        self, blocks: list[dict], question_info: dict | None
    ) -> list[dict]:
        """Get body blocks: after question line, excluding header."""
        if question_info is not None:
            start = question_info["block_index"] + 1
        else:
            start = 0
        return [b for b in blocks[start:] if b.get("type") != "header"]

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
        """Split body into preamble and sub-questions.

        Only single-letter (a)-(z) labels are top-level sub-questions,
        and only when they follow sequential alphabetical order.
        Nested labels like (i), (ii), (A), (B) stay inside their parent.
        """
        # Flatten all body blocks into text segments, each tagged with
        # whether it starts a new top-level sub-question candidate
        segments = self._flatten_to_segments(body_blocks)

        if not segments:
            return "", []

        # Collect candidate sub-question positions
        candidates: list[tuple[int, str]] = []  # (segment_index, label)
        for i, (text, label) in enumerate(segments):
            if label is not None:
                candidates.append((i, label))

        # Filter to only sequential top-level labels:
        # Start from (a), then expect (b), (c), ... in order.
        # Any label that breaks sequence is nested.
        sub_starts = self._filter_sequential_labels(candidates)

        if not sub_starts:
            # No sub-questions found
            all_text = "\n".join(text for text, _ in segments).strip()
            return all_text, []

        # Everything before the first sub-question is preamble
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

            # Remove the leading (label) from the text
            sub_text = self._strip_top_level_label_prefix(sub_text)

            marks = self._extract_marks(sub_text)
            cleaned_text = MARKS_RE.sub("", sub_text).strip()

            sub_questions.append(
                SubQuestion(label=label, text=cleaned_text, marks=marks)
            )

        return preamble, sub_questions

    def _flatten_to_segments(
        self, body_blocks: list[dict]
    ) -> list[tuple[str, str | None]]:
        """Flatten blocks into (text, top_level_label_or_None) segments.

        Each segment is a logical line of text. List items are split into
        separate segments. Only (a)-(z) single-letter labels are detected
        as top-level sub-question starts.
        """
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

    def _filter_sequential_labels(
        self, candidates: list[tuple[int, str]]
    ) -> list[tuple[int, str]]:
        """Filter candidates to only include sequentially ordered labels.

        Expects labels to follow alphabetical order starting from 'a'.
        Labels that break the sequence (like 'i' after 'b') are treated
        as nested and excluded.
        """
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
        """Detect a single-letter sub-question token at the start of text.

        This helper is intentionally low-level: it returns any matching
        lowercase label token, including noisy forms such as ``(i)``.
        Sequential filtering in ``_filter_sequential_labels`` decides whether
        a detected token is actually treated as a top-level sub-question.
        """
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
