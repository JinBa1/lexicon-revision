"""Parser regression tests over selected MinerU `content_list.json` fixtures.

This file is the main semantic contract for the Cambridge parser. Passing these
tests means the parser can recover the expected metadata and top-level question
structure from the current handpicked fixture set, including known edge cases
around lists, nested tiers, tables, images, and MinerU spacing noise.

Passing this file does NOT prove the parser is correct for the full Cambridge
corpus. It proves that the current parser behavior matches expectations on the
selected regression fixtures and helper-level edge cases encoded here.
"""

from __future__ import annotations

from src.chunking.cambridge_content_list_parser import CambridgeContentListParser


class TestHeaderParsing:
    """Header recovery from Cambridge Tripos fixture variants.

    Passing this category means the parser can recover tripos part/year/paper
    across the header layouts represented in the committed fixtures.
    """

    def test_header_2025_p1(self, content_list_q1: str) -> None:
        """Modern fixture: Part IA / 2025 / Paper 1 should parse cleanly."""
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_q1)
        assert len(results) == 1
        pq = results[0]
        assert pq.tripos_part == "Part IA"
        assert pq.year == 2025
        assert pq.paper == 1

    def test_header_2018_p1(self, content_list_code_2018_q3: str) -> None:
        """Older Part IA header layout should still parse cleanly."""
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_code_2018_q3)
        pq = results[0]
        assert pq.tripos_part == "Part IA"
        assert pq.year == 2018
        assert pq.paper == 1

    def test_header_2018_p8(self, content_list_table_2018_q7: str) -> None:
        """Part II fixtures must not be misclassified as Part IA or IB."""
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_table_2018_q7)
        pq = results[0]
        assert pq.tripos_part == "Part II"
        assert pq.year == 2018
        assert pq.paper == 8

    def test_header_2018_p6(self, content_list_formula_2018_q8: str) -> None:
        """Part IB header parsing is covered by a formula-heavy fixture."""
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_formula_2018_q8)
        pq = results[0]
        assert pq.tripos_part == "Part IB"
        assert pq.year == 2018
        assert pq.paper == 6


class TestQuestionLineParsing:
    """Question-line extraction for number/topic/author metadata.

    Passing this category means the parser can recover the canonical question
    identifier line from both modern and older Cambridge fixtures.
    """

    def test_q1_2025(self, content_list_q1: str) -> None:
        """Modern lowercase author token is parsed without fallback metadata."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        assert pq.question_number == 1
        assert pq.topic == "Foundations of Computer Science"
        assert pq.author == "avsm2"

    def test_q3_2025(self, content_list_q3: str) -> None:
        """Modern object-oriented programming question line parses cleanly."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        assert pq.question_number == 3
        assert pq.topic == "Object-Oriented Programming"
        assert pq.author == "rkh23"

    def test_q7_2025(self, content_list_q7: str) -> None:
        """Another modern question-line sample with a different topic/author."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        assert pq.question_number == 7
        assert pq.topic == "Algorithms 1"
        assert pq.author == "jkf21"

    def test_q3_2018_author_format(self, content_list_code_2018_q3: str) -> None:
        """2018 uses uppercase short author like 'RKH' not 'rkh23'."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_code_2018_q3)[0]
        assert pq.question_number == 3
        assert pq.topic == "Object-Oriented Programming"
        assert pq.author == "RKH"

    def test_q1_2018(self, content_list_tiers_2018_q1: str) -> None:
        """Older fixture with uppercase initials should still parse consistently."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_tiers_2018_q1)[0]
        assert pq.question_number == 1
        assert pq.topic == "Foundations of Computer Science"
        assert pq.author == "AM"


class TestMetadataNoiseTolerance:
    """Narrow tolerance to MinerU spacing noise in parser control tokens.

    Passing this category means the parser accepts benign spacing noise while
    staying structurally strict about what counts as a header/question line.
    """

    def test_parse_question_line_tolerates_author_bracket_spacing(self) -> None:
        """Whitespace inside author brackets must not break question-line parsing."""
        parser = CambridgeContentListParser()
        blocks = [{"type": "text", "text": "7 Algorithms 1 ( jkf21 )"}]
        result = parser._parse_question_line(blocks)
        assert result is not None
        assert result["question_number"] == 7
        assert result["topic"] == "Algorithms 1"
        assert result["author"] == "jkf21"

    def test_parse_header_tolerates_spacing_and_separator_variants(self) -> None:
        """Cambridge header matching tolerates dash/spacing variation only."""
        parser = CambridgeContentListParser()
        blocks = [
            {
                "type": "header",
                "text": "COMPUTER SCIENCE TRIPOS  Part IA - 2025 - Paper 1",
            }
        ]
        result = parser._parse_header(blocks)
        assert result == {
            "tripos_part": "Part IA",
            "year": 2025,
            "paper": 1,
        }


class TestSubQuestionSplitting:
    """Top-level sub-question detection and marks aggregation.

    Passing this category means the parser is honoring the project's core
    chunking rule: only top-level `(a)`, `(b)`, ... become sub-questions,
    while nested content stays inside the parent text.
    """

    def test_detect_top_level_label_tolerates_internal_spaces(self) -> None:
        """Spacing noise like `(d )` should not break top-level token detection."""
        parser = CambridgeContentListParser()
        assert parser._detect_top_level_label("(d) prompt") == "d"
        assert parser._detect_top_level_label("(d ) prompt") == "d"
        assert parser._detect_top_level_label("( d) prompt") == "d"
        assert parser._detect_top_level_label("( d ) prompt") == "d"

    def test_detect_top_level_label_matches_single_letter_token(self) -> None:
        """Low-level token detection still recognizes single-letter bracket tokens."""
        parser = CambridgeContentListParser()
        assert parser._detect_top_level_label("(i) nested") == "i"

    def test_prefix_stripping_tolerates_internal_spaces(self) -> None:
        """Stored sub-question text should lose only the noisy top-level prefix."""
        parser = CambridgeContentListParser()
        assert parser._strip_top_level_label_prefix("(d) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("(d ) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("( d) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("( d ) prompt") == "prompt"

    def test_q1_2025_sub_questions(self, content_list_q1: str) -> None:
        """Representative modern fixture splits into exactly three top-level parts."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c"]

    def test_q1_2025_marks(self, content_list_q1: str) -> None:
        """Sub-question marks and total marks are aggregated from part labels."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        marks = [sq.marks for sq in pq.sub_questions]
        assert marks == [10, 4, 6]
        assert pq.total_marks == 20

    def test_q7_2025_sub_questions(self, content_list_q7: str) -> None:
        """Equation-heavy fixture still yields four top-level parts."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c", "d"]

    def test_q7_2025_marks(self, content_list_q7: str) -> None:
        """Marks aggregation still works when equations are present in the text."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        marks = [sq.marks for sq in pq.sub_questions]
        assert marks == [7, 3, 7, 3]
        assert pq.total_marks == 20

    def test_q3_2025_two_top_level_subs(self, content_list_q3: str) -> None:
        """q3 has (a) and (b) as top-level; (i), (ii), (iii), (A), (B) are nested."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b"]

    def test_q3_2025_marks(self, content_list_q3: str) -> None:
        """Marks on nested items roll up into the parent top-level parts."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        # (a) has marks: 3+2+2+1=8, (b) has 12
        assert pq.sub_questions[0].marks == 8
        assert pq.sub_questions[1].marks == 12
        assert pq.total_marks == 20

    def test_q3_2025_preamble_content(self, content_list_q3: str) -> None:
        """Content before the first top-level part stays in the question preamble."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        assert "PriorityQueue" in pq.preamble

    def test_2018_q3_all_in_list(self, content_list_code_2018_q3: str) -> None:
        """y2018p1q3 has all sub-questions (a-e) in a single list block."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_code_2018_q3)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c", "d", "e"]

    def test_2018_q5_q7_top_level_labels_include_noisy_d(
        self, content_list_y2018p5q7: str
    ) -> None:
        """MinerU emits '(d )'; it should still be parsed as top-level d."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_y2018p5q7)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c", "d"]


class TestMarksNoiseTolerance:
    """Narrow tolerance to noisy spacing inside marks brackets."""

    def test_extract_marks_tolerates_spacing(self) -> None:
        """Spacing-only noise inside `[N marks]` should not lose marks metadata."""
        parser = CambridgeContentListParser()
        assert parser._extract_marks("Prompt [10 marks]") == 10
        assert parser._extract_marks("Prompt [10  marks]") == 10
        assert parser._extract_marks("Prompt [ 10 marks ]") == 10
        assert parser._extract_marks("Prompt [10 mark]") == 10

    def test_marks_regex_does_not_match_arbitrary_bracketed_number(self) -> None:
        """The parser must not treat any bracketed number as marks."""
        parser = CambridgeContentListParser()
        assert parser._extract_marks("Prompt [10]") is None


class TestTieredSubQuestions:
    """Nested tier handling within the top-level-only parser design.

    Passing this category means the parser is not inventing extra chunks for
    Roman-numeral or other nested tiers in the covered fixtures.
    """

    def test_2018_q1_top_level_subs(self, content_list_tiers_2018_q1: str) -> None:
        """y2018p1q1 has (a), (b), (c) as top-level. (i)-(iv) nested inside."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_tiers_2018_q1)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c"]

    def test_2018_q1_nested_content_in_parent(
        self, content_list_tiers_2018_q1: str
    ) -> None:
        """Nested (i)-(iv) content should appear inside parent sub-question text."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_tiers_2018_q1)[0]
        # (a) should contain the nested (i)-(iv) items
        a_text = pq.sub_questions[0].text
        assert "(i" in a_text
        # (c) should contain nested items too
        c_text = pq.sub_questions[2].text
        assert "map f" in c_text or "map" in c_text


class TestContentFlags:
    """Coarse content flags derived from MinerU block types.

    Passing this category means the parser is setting boolean summary flags
    correctly for the fixture types represented here. These flags are useful for
    filtering and debugging, but they are intentionally coarse.
    """

    def test_q1_2025_has_code(self, content_list_q1: str) -> None:
        """Code blocks should set `has_code` without implying figures or tables."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        assert pq.has_code is True
        assert pq.has_figure is False
        assert pq.has_table is False

    def test_q7_2025_equations_not_code(self, content_list_q7: str) -> None:
        """Equations should NOT set has_code."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        assert pq.has_code is False
        assert pq.has_figure is False
        assert pq.has_table is False

    def test_media_2018_q4_has_figure(self, content_list_media_2018_q4: str) -> None:
        """Image-bearing fixtures set `has_figure`."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_media_2018_q4)[0]
        assert pq.has_figure is True

    def test_table_2018_q7_has_table(self, content_list_table_2018_q7: str) -> None:
        """Table-bearing fixtures set `has_table`."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_table_2018_q7)[0]
        assert pq.has_table is True

    def test_code_2018_q3_has_code(self, content_list_code_2018_q3: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_code_2018_q3)[0]
        assert pq.has_code is True

    def test_formula_2018_q8_equations(self, content_list_formula_2018_q8: str) -> None:
        """Formula fixture has equations but no code blocks."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_formula_2018_q8)[0]
        assert pq.has_code is False


class TestEquationHandling:
    """Equation preservation without collapsing into `has_code`."""

    def test_q7_equations_in_sub_question_text(self, content_list_q7: str) -> None:
        """Equation text should remain in the owning sub-question body."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        # Sub-question (a) should contain the equation text
        a_text = pq.sub_questions[0].text
        assert "T (1) = 1" in a_text or "T(1)" in a_text

    def test_formula_2018_equations_in_text(
        self, content_list_formula_2018_q8: str
    ) -> None:
        """Formula-heavy fixtures should keep mathematical text in the parsed body."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_formula_2018_q8)[0]
        # Preamble should contain equation content
        assert "Petal" in pq.preamble or "alpha" in pq.preamble or "$$" in pq.preamble


class TestNoWarningsOnCleanInput:
    """Sanity checks for parser warnings on representative clean fixtures.

    Passing this category means the parser did not need to fall back or emit
    warning markers on these well-formed examples.
    """

    def test_q1_no_warnings(self, content_list_q1: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        assert pq.warnings == []

    def test_q7_no_warnings(self, content_list_q7: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        assert pq.warnings == []

    def test_q3_no_warnings(self, content_list_q3: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        assert pq.warnings == []


class TestEdgeCases:
    """Regression tests for concrete bugs discovered in real fixtures.

    Passing this category means the parser continues to handle the specific
    issues already found during manual inspection and debugging.
    """

    def test_2018_q3_preamble_has_code(self, content_list_code_2018_q3: str) -> None:
        """Code that appears before `(a)` must stay in the question preamble."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_code_2018_q3)[0]
        assert "Java" in pq.preamble or "class" in pq.preamble

    def test_media_2018_q4_sub_questions(self, content_list_media_2018_q4: str) -> None:
        """A figure in the preamble must not break later top-level splitting."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_media_2018_q4)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b"]

    def test_table_2018_q7_sub_questions(self, content_list_table_2018_q7: str) -> None:
        """A table between body text must not collapse `(a)` / `(b)` detection."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_table_2018_q7)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b"]

    def test_table_2018_q7_preserves_table_media_block(
        self, content_list_table_2018_q7: str
    ) -> None:
        """Parser preserves raw table block facts needed by the pipeline later."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_table_2018_q7)[0]

        assert len(pq.media_blocks) == 1

        table_block = pq.media_blocks[0]
        assert table_block.kind == "table"
        assert table_block.file_path == (
            "images/01517e12e06427e3b9dbeed8069cbe295315d166d69b631c325b584a083be757.jpg"
        )
        assert table_block.page_number == 1
        assert table_block.bbox == (247.0, 472.0, 771.0, 545.0)
        assert table_block.order_index == 2
        assert "<table>" in table_block.text_payload
        assert "doc3" in table_block.text_payload

    def test_table_2018_q7_preserves_owner_hint_and_text_flow(
        self, content_list_table_2018_q7: str
    ) -> None:
        """The preserved table remains inside part `(b)` and is hinted as such."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_table_2018_q7)[0]

        table_block = pq.media_blocks[0]
        sub_b = next(sq for sq in pq.sub_questions if sq.label == "b")

        assert table_block.owner_hint_label == "b"
        assert table_block.is_shared_candidate is False
        assert table_block.text_payload in sub_b.text

    def test_media_after_multi_label_list_inherits_last_top_level_label(self) -> None:
        """A media block after a mixed `(a)/(b)` list inherits the last label."""
        parser = CambridgeContentListParser()
        body_blocks = [
            {
                "type": "list",
                "list_items": [
                    "(a) First prompt. [2 marks]",
                    "(b) Second prompt. [3 marks]",
                ],
            },
            {
                "type": "table",
                "table_body": "<table><tr><td>value</td></tr></table>",
                "img_path": "images/table.jpg",
                "page_idx": 0,
                "bbox": [10, 20, 30, 40],
            },
        ]

        _, sub_questions = parser._split_sub_questions(body_blocks)
        media_blocks = parser._extract_media_blocks(body_blocks)

        assert [sq.label for sq in sub_questions] == ["a", "b"]
        assert len(media_blocks) == 1
        assert media_blocks[0].owner_hint_label == "b"
        assert media_blocks[0].is_shared_candidate is False

    def test_image_after_top_level_sub_question_inherits_owner_hint(self) -> None:
        """Images, not just tables, inherit the latest top-level owner hint."""
        parser = CambridgeContentListParser()
        body_blocks = [
            {"type": "text", "text": "(a) Prompt text. [2 marks]"},
            {
                "type": "image",
                "img_path": "images/figure.jpg",
                "page_idx": 0,
                "bbox": [11, 22, 33, 44],
            },
        ]

        _, sub_questions = parser._split_sub_questions(body_blocks)
        media_blocks = parser._extract_media_blocks(body_blocks)

        assert [sq.label for sq in sub_questions] == ["a"]
        assert len(media_blocks) == 1
        assert media_blocks[0].owner_hint_label == "a"
        assert media_blocks[0].is_shared_candidate is False

    def test_media_2018_q4_image_stays_shared_when_in_preamble(
        self, content_list_media_2018_q4: str
    ) -> None:
        """A preamble image stays unowned at parser stage and is marked shared."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_media_2018_q4)[0]

        assert len(pq.media_blocks) == 1
        image_block = pq.media_blocks[0]
        assert image_block.kind == "image"
        assert image_block.owner_hint_label is None
        assert image_block.is_shared_candidate is True
