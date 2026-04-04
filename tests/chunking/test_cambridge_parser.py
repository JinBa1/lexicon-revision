import fitz
from src.chunking.cambridge_parser import CambridgeParser


def test_parse_header_standard():
    parser = CambridgeParser()
    text = "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1\n"
    result = parser._parse_header(text)
    assert result == {"tripos_part": "Part IA", "year": 2025, "paper": 1}


def test_parse_header_with_hyphen():
    parser = CambridgeParser()
    text = "COMPUTER SCIENCE TRIPOS Part IB - 2024 - Paper 3\n"
    result = parser._parse_header(text)
    assert result == {"tripos_part": "Part IB", "year": 2024, "paper": 3}


def test_parse_header_no_match():
    parser = CambridgeParser()
    text = "Some other document header\n"
    result = parser._parse_header(text)
    assert result is None


def test_parse_question_line_single_author():
    parser = CambridgeParser()
    text = "7\tAlgorithms 1 (jkf21)"
    result = parser._parse_question_line(text)
    assert result == {
        "question_number": 7,
        "topic": "Algorithms 1",
        "author": "jkf21",
    }


def test_parse_question_line_multiple_authors():
    parser = CambridgeParser()
    text = "1\tFoundations of Computer Science (avsm2+jjl25)"
    result = parser._parse_question_line(text)
    assert result == {
        "question_number": 1,
        "topic": "Foundations of Computer Science",
        "author": "avsm2+jjl25",
    }


def test_parse_question_line_no_match():
    parser = CambridgeParser()
    text = "This is not a question line"
    result = parser._parse_question_line(text)
    assert result is None


def test_parse_real_pdf_header_and_question(sample_pdf_q1):
    """Parse a real Cambridge PDF and verify header + question metadata."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part == "Part IA"
    assert pq.year == 2025
    assert pq.paper == 1
    assert pq.question_number == 1
    assert pq.topic == "Foundations of Computer Science"
    assert pq.author == "avsm2"


def test_parse_real_pdf_header_and_question_q7(sample_pdf_q7):
    """Parse a different question to verify consistency."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q7)
    assert len(results) == 1
    pq = results[0]
    assert pq.question_number == 7
    assert pq.topic == "Algorithms 1"
    assert pq.author == "jkf21"


def test_old_layout_metadata_code_question(real_pdf_code_2018_q3):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_code_2018_q3)
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part == "Part IA"
    assert pq.year == 2018
    assert pq.paper == 1
    assert pq.question_number == 3
    assert pq.topic == "Object-Oriented Programming"
    assert pq.author == "RKH"


def test_old_layout_metadata_formula_question(real_pdf_formula_2018_q8):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_formula_2018_q8)
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part == "Part IB"
    assert pq.year == 2018
    assert pq.paper == 6
    assert pq.question_number == 8
    assert pq.topic == "Foundations of Data Science"
    assert pq.author == "DJW"


def test_old_layout_metadata_table_question(real_pdf_table_2018_q7):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_table_2018_q7)
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part == "Part II"
    assert pq.year == 2018
    assert pq.paper == 8
    assert pq.question_number == 7
    assert pq.topic == "Information Retrieval"
    assert pq.author == "HY"


def test_metadata_scan_continues_until_body_boundary():
    parser = CambridgeParser()
    rows = [
        {
            "page_number": 0,
            "page_height": 842.0,
            "x0": 72.0,
            "y0": 72.0,
            "x1": 320.0,
            "y1": 84.0,
            "text": "COMPUTER SCIENCE TRIPOS Part IA – 2018 – Paper 1",
            "has_code": False,
        }
    ]
    rows.extend(
        {
            "page_number": 0,
            "page_height": 842.0,
            "x0": 100.0,
            "y0": 100.0 + offset,
            "x1": 320.0,
            "y1": 112.0 + offset,
            "text": f"cover line {offset}",
            "has_code": False,
        }
        for offset in range(0, 90, 10)
    )
    rows.extend(
        [
            {
                "page_number": 0,
                "page_height": 842.0,
                "x0": 80.0,
                "y0": 205.0,
                "x1": 88.0,
                "y1": 217.0,
                "text": "11",
                "has_code": False,
            },
            {
                "page_number": 0,
                "page_height": 842.0,
                "x0": 99.0,
                "y0": 205.0,
                "x1": 310.0,
                "y1": 217.0,
                "text": "Lambda Calculus (LAM)",
                "has_code": False,
            },
            {
                "page_number": 0,
                "page_height": 842.0,
                "x0": 99.0,
                "y0": 240.0,
                "x1": 310.0,
                "y1": 252.0,
                "text": "(a) Explain beta reduction. [10 marks]",
                "has_code": False,
            },
        ]
    )

    result = parser._parse_question_info_from_rows(rows, header_index=0)

    assert result is not None
    assert result["question_number"] == 11
    assert result["topic"] == "Lambda Calculus"
    assert result["author"] == "LAM"


def test_split_sub_questions_q1(sample_pdf_q1):
    """Q1 has 3 sub-questions: (a) [10], (b) [4], (c) [6]."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    pq = results[0]
    assert len(pq.sub_questions) == 3
    assert [sq.label for sq in pq.sub_questions] == ["a", "b", "c"]


def test_sub_question_marks_q1(sample_pdf_q1):
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    pq = results[0]
    assert pq.sub_questions[0].marks == 10
    assert pq.sub_questions[1].marks == 4
    assert pq.sub_questions[2].marks == 6
    assert pq.total_marks == 20


def test_sub_question_marks_q7(sample_pdf_q7):
    """Q7 has 4 sub-questions: (a) [7], (b) [3], (c) [7], (d) [3]."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q7)
    pq = results[0]
    assert len(pq.sub_questions) == 4
    assert [sq.marks for sq in pq.sub_questions] == [7, 3, 7, 3]
    assert pq.total_marks == 20


def test_top_level_split_old_layout_tiers_question(real_pdf_tiers_2018_q1):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_tiers_2018_q1)
    pq = results[0]
    assert [sq.label for sq in pq.sub_questions] == ["a", "b", "c"]


def test_nested_v_stays_inside_parent_c_text(real_pdf_tiers_2018_q1):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_tiers_2018_q1)
    pq = results[0]
    assert "map map zs = [[1,2],[3,4]]" in pq.sub_questions[-1].text
    assert "(v)" in pq.sub_questions[-1].text
    assert all(sq.label != "v" for sq in pq.sub_questions)


def test_top_level_split_table_question(real_pdf_table_2018_q7):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_table_2018_q7)
    pq = results[0]
    assert [sq.label for sq in pq.sub_questions] == ["a", "b"]
    assert "(ii)" in pq.sub_questions[0].text or "(ii)" in pq.sub_questions[1].text


def test_top_level_split_media_question(real_pdf_media_2018_q4):
    parser = CambridgeParser()
    results = parser.parse(real_pdf_media_2018_q4)
    pq = results[0]
    assert [sq.label for sq in pq.sub_questions] == ["a", "b"]
    assert "(ii)" in pq.sub_questions[0].text
    assert "(iii)" in pq.sub_questions[0].text
    assert "(ii)" in pq.sub_questions[1].text


def test_top_level_split_ignores_nested_single_letter_near_margin(tmp_path):
    pdf_path = tmp_path / "nested_single_letter.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1",
    )
    page.insert_text((80, 100), "5")
    page.insert_text((99, 100), "Parsing (prs1)")
    page.insert_text((99, 132), "(a) Parent discussion starts here.")
    page.insert_text((104, 150), "(b) nested example that must stay inside (a).")
    page.insert_text((99, 182), "(c) Separate top-level part. [10 marks]")
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    pq = results[0]

    assert [sq.label for sq in pq.sub_questions] == ["a", "c"]
    assert "(b) nested example that must stay inside (a)." in pq.sub_questions[0].text
    assert all(sq.label != "b" for sq in pq.sub_questions)


def test_top_level_split_ignores_first_candidate_noise(tmp_path):
    pdf_path = tmp_path / "first_candidate_noise.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1")
    page.insert_text((80, 100), "6")
    page.insert_text((99, 100), "Compilers (cmp1)")
    page.insert_text((130, 132), "(a) note in the preamble, not a top-level split.")
    page.insert_text((99, 168), "(a) Real top-level first part. [10 marks]")
    page.insert_text((99, 204), "(b) Real top-level second part. [10 marks]")
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    pq = results[0]

    assert [sq.label for sq in pq.sub_questions] == ["a", "b"]
    assert "(a) note in the preamble, not a top-level split." in pq.preamble


def test_top_level_split_ignores_same_indent_preamble_line(tmp_path):
    pdf_path = tmp_path / "preamble_line.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1")
    page.insert_text((80, 100), "8")
    page.insert_text((99, 100), "Logic (log1)")
    page.insert_text((99, 132), "(a) Note: read all parts carefully before answering.")
    page.insert_text((99, 168), "(a) Real top-level first part. [8 marks]")
    page.insert_text((99, 204), "(b) Real top-level second part. [12 marks]")
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    pq = results[0]

    assert [sq.label for sq in pq.sub_questions] == ["a", "b"]
    assert "(a) Note: read all parts carefully before answering." in pq.preamble


def test_top_level_split_ignores_nested_single_letter_after_marks_line(tmp_path):
    pdf_path = tmp_path / "nested_after_marks_line.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1")
    page.insert_text((80, 100), "7")
    page.insert_text((99, 100), "Semantics (sem1)")
    page.insert_text((99, 132), "(a) Parent text starts here.")
    page.insert_text((482, 150), "[3 marks]")
    page.insert_text(
        (104, 168), "(b) nested marker after marks line that stays in (a)."
    )
    page.insert_text((99, 204), "(c) Next real top-level part. [17 marks]")
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    pq = results[0]

    assert [sq.label for sq in pq.sub_questions] == ["a", "c"]
    assert (
        "(b) nested marker after marks line that stays in (a)."
        in pq.sub_questions[0].text
    )
    assert all(sq.label != "b" for sq in pq.sub_questions)


def test_merge_line_fragments_does_not_merge_far_same_block_fragments():
    parser = CambridgeParser()
    fragments = [
        {
            "page_number": 0,
            "block_index": 4,
            "page_height": 842.0,
            "x0": 80.0,
            "y0": 100.0,
            "x1": 120.0,
            "y1": 112.0,
            "text": "left",
            "has_code": False,
        },
        {
            "page_number": 0,
            "block_index": 4,
            "page_height": 842.0,
            "x0": 320.0,
            "y0": 100.5,
            "x1": 360.0,
            "y1": 112.5,
            "text": "right",
            "has_code": False,
        },
    ]

    rows = parser._merge_line_fragments(fragments)

    assert [row["text"] for row in rows] == ["left", "right"]


def test_merge_line_fragments_does_not_merge_close_cross_block_fragments():
    parser = CambridgeParser()
    fragments = [
        {
            "page_number": 0,
            "block_index": 4,
            "page_height": 842.0,
            "x0": 80.0,
            "y0": 100.0,
            "x1": 120.0,
            "y1": 112.0,
            "text": "left",
            "has_code": False,
        },
        {
            "page_number": 0,
            "block_index": 5,
            "page_height": 842.0,
            "x0": 130.0,
            "y0": 100.5,
            "x1": 170.0,
            "y1": 112.5,
            "text": "right",
            "has_code": False,
        },
    ]

    rows = parser._merge_line_fragments(fragments)

    assert [row["text"] for row in rows] == ["left", "right"]


def test_preamble_extraction_q3(sample_pdf_q3):
    """Q3 has a substantial preamble with WorkTask class before (a)."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q3)
    pq = results[0]
    assert "PriorityQueue" in pq.preamble
    assert "WorkTask" in pq.preamble
    assert len(pq.sub_questions) == 2


def test_marks_stripped_from_text(sample_pdf_q1):
    """Mark annotations like [10 marks] should be removed from stored text."""
    import re

    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    pq = results[0]
    for sq in pq.sub_questions:
        assert "[marks]" not in sq.text
        assert "[mark]" not in sq.text
        assert not re.search(r"\[\d+\s+marks?\]", sq.text)


def test_has_code_flag_q1(sample_pdf_q1):
    """Q1 contains OCaml code blocks — has_code should be True."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    assert results[0].has_code is True


def test_sub_question_text_contains_content(sample_pdf_q1):
    """Sub-question text should contain meaningful content, not be empty."""
    parser = CambridgeParser()
    results = parser.parse(sample_pdf_q1)
    pq = results[0]
    for sq in pq.sub_questions:
        assert len(sq.text) > 10, f"Sub-question ({sq.label}) text too short"


def test_partial_parse_bad_header(tmp_path):
    """If header doesn't match but text exists, emit chunk with warnings."""
    pdf_path = tmp_path / "bad_header.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72), "NOT A STANDARD HEADER\n\n(a) Some question text [5 marks]"
    )
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part is None
    assert pq.year is None
    assert "header_parse_failed" in pq.warnings


def test_no_sub_questions_is_valid(tmp_path):
    """A question with no (a)/(b)/(c) splits is valid, not an error."""
    pdf_path = tmp_path / "no_subs.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "COMPUTER SCIENCE TRIPOS Part IA – 2025 – Paper 1\n\n"
        "1 Some Topic (abc1)\n\n"
        "Explain the concept of recursion. [20 marks]",
    )
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    assert len(results) == 1
    pq = results[0]
    assert pq.tripos_part == "Part IA"
    assert pq.question_number == 1
    assert len(pq.sub_questions) == 0
    assert pq.warnings == []


def test_empty_pdf_returns_empty(tmp_path):
    """A PDF with no text at all should return empty list."""
    pdf_path = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    parser = CambridgeParser()
    results = parser.parse(str(pdf_path))
    assert results == []
