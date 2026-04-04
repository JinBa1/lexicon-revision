from __future__ import annotations

import re
from collections.abc import Iterable

import fitz
from src.chunking.base_parser import BaseParser
from src.chunking.models import ParsedQuestion, SubQuestion

HEADER_RE = re.compile(
    r"COMPUTER SCIENCE TRIPOS\s+Part\s+([A-Z]+)\s*[–·-]\s*(\d{4})\s*[–·-]\s*"
    r"Paper\s+(\d+)"
)
QUESTION_LINE_RE = re.compile(
    r"^(?P<number>\d+)[ \t]+(?P<topic>.+?)\s+\((?P<author>[A-Za-z0-9+]+)\)\s*$",
    re.MULTILINE,
)
TOPIC_LINE_RE = re.compile(
    r"^(?P<topic>.+?)\s+\((?P<author>[A-Za-z0-9+]+)\)\s*$",
    re.MULTILINE,
)
SUB_QUESTION_RE = re.compile(r"^\(([a-z])\)(?:\s+|$)")
FIRST_SUB_QUESTION_RE = re.compile(r"^\(a\)(?:\s+|$)")
MARKS_RE = re.compile(r"\[(\d+)\s+marks?\]")
MONOSPACE_FONTS = {"courier", "consolas", "menlo", "monaco", "dejavu sans mono", "cmtt"}
ROW_Y_TOLERANCE = 3.0
ROW_X_GAP_TOLERANCE = 36.0
TOP_LEVEL_X_TOLERANCE = 8.0
DEDENT_X_TOLERANCE = 1.0


class CambridgeParser(BaseParser):
    def parse(self, pdf_path: str) -> list[ParsedQuestion]:
        document = fitz.open(pdf_path)
        warnings: list[str] = []

        try:
            rows, has_code, has_figure = self._extract_rows(document)
        finally:
            document.close()

        full_text = self._rows_to_text(rows)
        if not full_text:
            return []

        header = self._parse_header(full_text)
        header_index = self._find_header_row_index(rows)
        question_info = self._parse_question_info_from_rows(rows, header_index)
        body_rows = self._extract_body_rows(rows, header_index, question_info)
        preamble, sub_questions = self._split_sub_questions(body_rows)

        if header is None:
            warnings.append("header_parse_failed")
        if question_info is None:
            warnings.append("question_line_parse_failed")

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
                warnings=warnings,
            )
        ]

    def _parse_header(self, text: str) -> dict[str, int | str] | None:
        match = HEADER_RE.search(text)
        if not match:
            return None

        return {
            "tripos_part": f"Part {match.group(1)}",
            "year": int(match.group(2)),
            "paper": int(match.group(3)),
        }

    def _parse_question_line(self, text: str) -> dict[str, int | str] | None:
        direct_match = QUESTION_LINE_RE.search(text)
        if direct_match:
            return {
                "question_number": int(direct_match.group("number")),
                "topic": direct_match.group("topic").strip(),
                "author": direct_match.group("author"),
            }

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines[:-2]):
            if not line.isdigit():
                continue
            if self._parse_header(lines[index + 1]) is None:
                continue
            topic_match = TOPIC_LINE_RE.match(lines[index + 2])
            if topic_match:
                return {
                    "question_number": int(line),
                    "topic": topic_match.group("topic").strip(),
                    "author": topic_match.group("author"),
                }

        return None

    def _extract_rows(
        self, document: fitz.Document
    ) -> tuple[list[dict[str, int | float | str | bool]], bool, bool]:
        rows: list[dict[str, int | float | str | bool]] = []
        has_code = False
        has_figure = False

        for page_number, page in enumerate(document):
            page_dict = page.get_text("dict")
            fragments: list[dict[str, int | float | str | bool]] = []

            for block in page_dict.get("blocks", []):
                if block.get("type") == 1:
                    has_figure = True
                    continue

                if block.get("type") != 0:
                    continue

                for line in block.get("lines", []):
                    text_parts: list[str] = []
                    line_has_code = False
                    for span in line.get("spans", []):
                        text_parts.append(span.get("text", ""))
                        font_name = span.get("font", "").lower()
                        if any(mono in font_name for mono in MONOSPACE_FONTS):
                            line_has_code = True

                    text = "".join(text_parts).strip()
                    if not text:
                        continue

                    x0, y0, x1, y1 = line.get("bbox", (0.0, 0.0, 0.0, 0.0))
                    fragments.append(
                        {
                            "page_number": page_number,
                            "block_index": int(block.get("number", -1)),
                            "page_height": float(page.rect.height),
                            "x0": float(x0),
                            "y0": float(y0),
                            "x1": float(x1),
                            "y1": float(y1),
                            "text": text,
                            "has_code": line_has_code,
                        }
                    )
                    has_code = has_code or line_has_code

            rows.extend(self._merge_line_fragments(fragments))

        return rows, has_code, has_figure

    def _merge_line_fragments(
        self, fragments: Iterable[dict[str, int | float | str | bool]]
    ) -> list[dict[str, int | float | str | bool]]:
        ordered_fragments = sorted(
            fragments,
            key=lambda fragment: (
                int(fragment["page_number"]),
                float(fragment["y0"]),
                float(fragment["x0"]),
            ),
        )
        rows: list[dict[str, int | float | str | bool]] = []
        current_parts: list[dict[str, int | float | str | bool]] = []

        def flush_current() -> None:
            if not current_parts:
                return
            parts = sorted(current_parts, key=lambda part: float(part["x0"]))
            text_parts = [
                str(part["text"]).strip() for part in parts if str(part["text"]).strip()
            ]
            text = " ".join(text_parts)
            if not text:
                return
            row = {
                "page_number": int(parts[0]["page_number"]),
                "block_index": int(parts[0]["block_index"]),
                "page_height": float(parts[0]["page_height"]),
                "x0": min(float(part["x0"]) for part in parts),
                "y0": min(float(part["y0"]) for part in parts),
                "x1": max(float(part["x1"]) for part in parts),
                "y1": max(float(part["y1"]) for part in parts),
                "text": text,
                "has_code": any(bool(part["has_code"]) for part in parts),
            }
            if not self._is_probable_page_number_row(row):
                rows.append(row)

        for fragment in ordered_fragments:
            if not current_parts:
                current_parts = [fragment]
                continue

            same_page = int(fragment["page_number"]) == int(
                current_parts[0]["page_number"]
            )
            same_row = (
                abs(float(fragment["y0"]) - float(current_parts[0]["y0"]))
                <= ROW_Y_TOLERANCE
            )
            horizontal_gap = float(fragment["x0"]) - max(
                float(part["x1"]) for part in current_parts
            )
            gap_is_small = horizontal_gap <= ROW_X_GAP_TOLERANCE
            same_block = int(fragment["block_index"]) == int(
                current_parts[-1]["block_index"]
            )

            if same_page and same_row and same_block and gap_is_small:
                current_parts.append(fragment)
                continue

            flush_current()
            current_parts = [fragment]

        flush_current()
        return rows

    def _is_probable_page_number_row(
        self, row: dict[str, int | float | str | bool]
    ) -> bool:
        text = str(row["text"]).strip()
        return text.isdigit() and float(row["y0"]) >= float(row["page_height"]) * 0.9

    def _rows_to_text(self, rows: list[dict[str, int | float | str | bool]]) -> str:
        return "\n".join(str(row["text"]) for row in rows).strip()

    def _find_header_row_index(
        self, rows: list[dict[str, int | float | str | bool]]
    ) -> int | None:
        for index, row in enumerate(rows):
            if self._parse_header(str(row["text"])) is not None:
                return index
        return None

    def _parse_question_info_from_rows(
        self, rows: list[dict[str, int | float | str | bool]], header_index: int | None
    ) -> dict[str, int | str] | None:
        start = header_index + 1 if header_index is not None else 0
        stop = self._find_question_info_search_stop(rows, start)

        for index in range(start, stop):
            text = str(rows[index]["text"]).strip()
            question_info = self._parse_question_line(text)
            if question_info is not None:
                return {**question_info, "body_start_index": index + 1}

            if not text.isdigit() or index + 1 >= stop:
                continue

            topic_match = TOPIC_LINE_RE.match(str(rows[index + 1]["text"]).strip())
            if topic_match:
                return {
                    "question_number": int(text),
                    "topic": topic_match.group("topic").strip(),
                    "author": topic_match.group("author"),
                    "body_start_index": index + 2,
                }

        return None

    def _find_question_info_search_stop(
        self, rows: list[dict[str, int | float | str | bool]], start_index: int
    ) -> int:
        for index in range(start_index, len(rows)):
            if FIRST_SUB_QUESTION_RE.match(str(rows[index]["text"]).strip()):
                return index
        return len(rows)

    def _extract_body_rows(
        self,
        rows: list[dict[str, int | float | str | bool]],
        header_index: int | None,
        question_info: dict[str, int | str] | None,
    ) -> list[dict[str, int | float | str | bool]]:
        if question_info is not None:
            start_index = int(question_info["body_start_index"])
        elif header_index is not None:
            start_index = header_index + 1
        else:
            start_index = 0

        return rows[start_index:]

    def _split_sub_questions(
        self, body_rows: list[dict[str, int | float | str | bool]]
    ) -> tuple[str, list[SubQuestion]]:
        top_level_splits = self._find_top_level_sub_question_rows(body_rows)
        if not top_level_splits:
            return self._rows_to_text(body_rows), []

        preamble = self._rows_to_text(body_rows[: top_level_splits[0][0]])
        sub_questions: list[SubQuestion] = []

        for index, (row_index, label) in enumerate(top_level_splits):
            start_row = body_rows[row_index]
            end_row_index = (
                top_level_splits[index + 1][0]
                if index + 1 < len(top_level_splits)
                else len(body_rows)
            )
            sub_rows = body_rows[row_index:end_row_index]
            first_row_text = SUB_QUESTION_RE.sub(
                "", str(start_row["text"]), count=1
            ).strip()
            row_texts = [first_row_text] if first_row_text else []
            row_texts.extend(str(row["text"]) for row in sub_rows[1:])
            sub_text = "\n".join(row_texts).strip()
            marks = self._extract_marks(sub_text)
            cleaned_text = MARKS_RE.sub("", sub_text).strip()
            sub_questions.append(
                SubQuestion(label=label, text=cleaned_text, marks=marks)
            )

        return preamble, sub_questions

    def _find_top_level_sub_question_rows(
        self, body_rows: list[dict[str, int | float | str | bool]]
    ) -> list[tuple[int, str]]:
        candidates: list[tuple[int, str, float]] = []

        for index, row in enumerate(body_rows):
            match = SUB_QUESTION_RE.match(str(row["text"]).strip())
            if match is None:
                continue
            candidates.append((index, match.group(1), float(row["x0"])))

        if not candidates:
            return []

        top_level_x = self._infer_top_level_x(candidates)
        aligned_candidates = [
            candidate
            for candidate in candidates
            if abs(candidate[2] - top_level_x) <= TOP_LEVEL_X_TOLERANCE
        ]
        start_position = self._find_first_top_level_candidate_position(
            aligned_candidates
        )
        top_level_rows: list[tuple[int, str]] = []

        for position, (index, label, _) in enumerate(aligned_candidates):
            if position < start_position:
                continue
            if not top_level_rows:
                top_level_rows.append((index, label))
                continue
            if self._is_top_level_sub_question_boundary(body_rows, index, top_level_x):
                top_level_rows.append((index, label))

        return top_level_rows

    def _infer_top_level_x(self, candidates: list[tuple[int, str, float]]) -> float:
        a_positions = [x0 for _, label, x0 in candidates if label == "a"]
        if a_positions:
            return self._select_anchor_x(a_positions)

        likely_top_level_positions = [x0 for _, _, x0 in candidates]
        return self._select_anchor_x(likely_top_level_positions)

    def _select_anchor_x(self, positions: list[float]) -> float:
        clusters: list[list[float]] = []

        for position in sorted(positions):
            for cluster in clusters:
                if abs(position - cluster[0]) <= TOP_LEVEL_X_TOLERANCE:
                    cluster.append(position)
                    break
            else:
                clusters.append([position])

        best_cluster = min(
            clusters,
            key=lambda cluster: (-len(cluster), min(cluster)),
        )
        return min(best_cluster)

    def _find_first_top_level_candidate_position(
        self, candidates: list[tuple[int, str, float]]
    ) -> int:
        if not candidates:
            return 0

        for position in range(len(candidates) - 1, -1, -1):
            if candidates[position][1] != "a":
                continue
            if any(
                next_label != "a" for _, next_label, _ in candidates[position + 1 :]
            ):
                return position

        a_positions = [
            position
            for position, (_, label, _) in enumerate(candidates)
            if label == "a"
        ]
        if a_positions:
            return a_positions[-1]
        return 0

    def _is_top_level_sub_question_boundary(
        self,
        body_rows: list[dict[str, int | float | str | bool]],
        row_index: int,
        top_level_x: float,
    ) -> bool:
        previous_row = body_rows[row_index - 1]
        previous_text = str(previous_row["text"]).strip()
        previous_meaningful_row = self._find_previous_non_marks_row(
            body_rows, row_index - 1
        )
        previous_meaningful_text = (
            str(previous_meaningful_row["text"]).strip()
            if previous_meaningful_row is not None
            else previous_text
        )
        current_x0 = float(body_rows[row_index]["x0"])
        previous_x0 = (
            float(previous_meaningful_row["x0"])
            if previous_meaningful_row is not None
            else float(previous_row["x0"])
        )

        if (
            self._extract_marks(previous_text) is not None
            and abs(current_x0 - top_level_x) <= DEDENT_X_TOLERANCE
        ):
            return True

        if current_x0 + DEDENT_X_TOLERANCE < previous_x0:
            return True

        return (
            SUB_QUESTION_RE.match(previous_meaningful_text) is None
            and abs(current_x0 - top_level_x) <= DEDENT_X_TOLERANCE
        )

    def _find_previous_non_marks_row(
        self,
        body_rows: list[dict[str, int | float | str | bool]],
        start_index: int,
    ) -> dict[str, int | float | str | bool] | None:
        for index in range(start_index, -1, -1):
            row = body_rows[index]
            if not self._is_marks_only_row(str(row["text"]).strip()):
                return row
        return None

    def _is_marks_only_row(self, text: str) -> bool:
        return bool(text) and not MARKS_RE.sub("", text).strip()

    def _extract_marks(self, text: str) -> int | None:
        matches = MARKS_RE.findall(text)
        if not matches:
            return None
        return int(matches[-1])

    def _compute_total_marks(self, sub_questions: list[SubQuestion]) -> int | None:
        if not sub_questions:
            return None
        marks = [sub_question.marks for sub_question in sub_questions]
        if any(mark is None for mark in marks):
            return None
        return sum(mark for mark in marks if mark is not None)
