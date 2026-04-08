"""Tests for CambridgeContentListParser against MinerU content_list.json fixtures."""

from __future__ import annotations

from src.chunking.cambridge_content_list_parser import CambridgeContentListParser


class TestHeaderParsing:
    """Test header extraction from content_list.json files."""

    def test_header_2025_p1(self, content_list_q1: str) -> None:
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_q1)
        assert len(results) == 1
        pq = results[0]
        assert pq.tripos_part == "Part IA"
        assert pq.year == 2025
        assert pq.paper == 1

    def test_header_2018_p1(self, content_list_code_2018_q3: str) -> None:
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_code_2018_q3)
        pq = results[0]
        assert pq.tripos_part == "Part IA"
        assert pq.year == 2018
        assert pq.paper == 1

    def test_header_2018_p8(self, content_list_table_2018_q7: str) -> None:
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_table_2018_q7)
        pq = results[0]
        assert pq.tripos_part == "Part II"
        assert pq.year == 2018
        assert pq.paper == 8

    def test_header_2018_p6(self, content_list_formula_2018_q8: str) -> None:
        parser = CambridgeContentListParser()
        results = parser.parse(content_list_formula_2018_q8)
        pq = results[0]
        assert pq.tripos_part == "Part IB"
        assert pq.year == 2018
        assert pq.paper == 6


class TestQuestionLineParsing:
    """Test question number, topic, and author extraction."""

    def test_q1_2025(self, content_list_q1: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        assert pq.question_number == 1
        assert pq.topic == "Foundations of Computer Science"
        assert pq.author == "avsm2"

    def test_q3_2025(self, content_list_q3: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        assert pq.question_number == 3
        assert pq.topic == "Object-Oriented Programming"
        assert pq.author == "rkh23"

    def test_q7_2025(self, content_list_q7: str) -> None:
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
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_tiers_2018_q1)[0]
        assert pq.question_number == 1
        assert pq.topic == "Foundations of Computer Science"
        assert pq.author == "AM"


class TestMetadataNoiseTolerance:
    """Test parsing of noisy metadata tokens without fuzzy inference."""

    def test_parse_question_line_tolerates_author_bracket_spacing(self) -> None:
        parser = CambridgeContentListParser()
        blocks = [{"type": "text", "text": "7 Algorithms 1 ( jkf21 )"}]
        result = parser._parse_question_line(blocks)
        assert result is not None
        assert result["question_number"] == 7
        assert result["topic"] == "Algorithms 1"
        assert result["author"] == "jkf21"

    def test_parse_header_tolerates_spacing_and_separator_variants(self) -> None:
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
    """Test sub-question detection and splitting."""

    def test_detect_top_level_label_tolerates_internal_spaces(self) -> None:
        parser = CambridgeContentListParser()
        assert parser._detect_top_level_label("(d) prompt") == "d"
        assert parser._detect_top_level_label("(d ) prompt") == "d"
        assert parser._detect_top_level_label("( d) prompt") == "d"
        assert parser._detect_top_level_label("( d ) prompt") == "d"

    def test_detect_top_level_label_matches_single_letter_token(self) -> None:
        parser = CambridgeContentListParser()
        assert parser._detect_top_level_label("(i) nested") == "i"

    def test_prefix_stripping_tolerates_internal_spaces(self) -> None:
        parser = CambridgeContentListParser()
        assert parser._strip_top_level_label_prefix("(d) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("(d ) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("( d) prompt") == "prompt"
        assert parser._strip_top_level_label_prefix("( d ) prompt") == "prompt"

    def test_q1_2025_sub_questions(self, content_list_q1: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c"]

    def test_q1_2025_marks(self, content_list_q1: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q1)[0]
        marks = [sq.marks for sq in pq.sub_questions]
        assert marks == [10, 4, 6]
        assert pq.total_marks == 20

    def test_q7_2025_sub_questions(self, content_list_q7: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b", "c", "d"]

    def test_q7_2025_marks(self, content_list_q7: str) -> None:
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
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q3)[0]
        # (a) has marks: 3+2+2+1=8, (b) has 12
        assert pq.sub_questions[0].marks == 8
        assert pq.sub_questions[1].marks == 12
        assert pq.total_marks == 20

    def test_q3_2025_preamble_content(self, content_list_q3: str) -> None:
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
    """Test marks extraction with noisy bracket spacing."""

    def test_extract_marks_tolerates_spacing(self) -> None:
        parser = CambridgeContentListParser()
        assert parser._extract_marks("Prompt [10 marks]") == 10
        assert parser._extract_marks("Prompt [10  marks]") == 10
        assert parser._extract_marks("Prompt [ 10 marks ]") == 10
        assert parser._extract_marks("Prompt [10 mark]") == 10

    def test_marks_regex_does_not_match_arbitrary_bracketed_number(self) -> None:
        parser = CambridgeContentListParser()
        assert parser._extract_marks("Prompt [10]") is None


class TestTieredSubQuestions:
    """Test that nested sub-questions stay inside their parent."""

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
    """Test has_code, has_figure, has_table detection."""

    def test_q1_2025_has_code(self, content_list_q1: str) -> None:
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
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_media_2018_q4)[0]
        assert pq.has_figure is True

    def test_table_2018_q7_has_table(self, content_list_table_2018_q7: str) -> None:
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
    """Test that equations are included in text content."""

    def test_q7_equations_in_sub_question_text(self, content_list_q7: str) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_q7)[0]
        # Sub-question (a) should contain the equation text
        a_text = pq.sub_questions[0].text
        assert "T (1) = 1" in a_text or "T(1)" in a_text

    def test_formula_2018_equations_in_text(
        self, content_list_formula_2018_q8: str
    ) -> None:
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_formula_2018_q8)[0]
        # Preamble should contain equation content
        assert "Petal" in pq.preamble or "alpha" in pq.preamble or "$$" in pq.preamble


class TestNoWarningsOnCleanInput:
    """Verify no parse warnings on well-formed fixtures."""

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
    """Test edge cases and robustness."""

    def test_2018_q3_preamble_has_code(self, content_list_code_2018_q3: str) -> None:
        """Preamble should include 'Consider the following Java class'."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_code_2018_q3)[0]
        assert "Java" in pq.preamble or "class" in pq.preamble

    def test_media_2018_q4_sub_questions(self, content_list_media_2018_q4: str) -> None:
        """y2018p1q4 should have (a) and (b) as top-level subs."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_media_2018_q4)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b"]

    def test_table_2018_q7_sub_questions(self, content_list_table_2018_q7: str) -> None:
        """y2018p8q7 should have (a) and (b) as top-level subs."""
        parser = CambridgeContentListParser()
        pq = parser.parse(content_list_table_2018_q7)[0]
        labels = [sq.label for sq in pq.sub_questions]
        assert labels == ["a", "b"]
