from src.chunking.models import Chunk, MediaRef, ParsedQuestion, SubQuestion


def test_sub_question_construction():
    sq = SubQuestion(label="a", text="Compare Comparable and Comparator.", marks=3)
    assert sq.label == "a"
    assert sq.marks == 3


def test_parsed_question_construction():
    sq = SubQuestion(label="a", text="Some text.", marks=5)
    pq = ParsedQuestion(
        tripos_part="Part IA",
        year=2025,
        paper=1,
        question_number=3,
        topic="Object-Oriented Programming",
        author="rkh23",
        preamble="The Java Collections framework...",
        sub_questions=[sq],
        total_marks=5,
        has_code=True,
        has_figure=False,
        has_table=False,
        warnings=[],
    )
    assert pq.tripos_part == "Part IA"
    assert pq.sub_questions[0].label == "a"
    assert pq.total_marks == 5


def test_media_ref_construction():
    mr = MediaRef(
        file_path="data/media/cam-2025-p1-q3-b/figure_1.png",
        page_number=1,
        bbox=(100.0, 200.0, 300.0, 400.0),
        chunk_id="cam-2025-p1-q3-b",
        description=None,
    )
    assert mr.page_number == 1
    assert mr.bbox == (100.0, 200.0, 300.0, 400.0)
    assert mr.description is None


def test_chunk_construction_question_level():
    chunk = Chunk(
        id="cam-2025-p1-q1",
        chunk_level="question",
        parent_chunk_id=None,
        text="Foundations of Computer Science...",
        year=2025,
        paper=1,
        question_number=1,
        topic="Foundations of Computer Science",
        author="avsm2",
        tripos_part="Part IA",
        sub_question_label=None,
        marks=None,
        total_marks=20,
        has_code=True,
        has_figure=False,
        has_table=False,
        media=[],
        source_pdf="y2025p1q1.pdf",
        warnings=[],
    )
    assert chunk.id == "cam-2025-p1-q1"
    assert chunk.chunk_level == "question"
    assert chunk.parent_chunk_id is None


def test_chunk_construction_sub_question_level():
    chunk = Chunk(
        id="cam-2025-p1-q1-a",
        chunk_level="sub_question",
        parent_chunk_id="cam-2025-p1-q1",
        text="Given the following incorrect code...",
        year=2025,
        paper=1,
        question_number=1,
        topic="Foundations of Computer Science",
        author="avsm2",
        tripos_part="Part IA",
        sub_question_label="a",
        marks=10,
        total_marks=20,
        has_code=True,
        has_figure=False,
        has_table=False,
        media=[],
        source_pdf="y2025p1q1.pdf",
        warnings=[],
    )
    assert chunk.chunk_level == "sub_question"
    assert chunk.parent_chunk_id == "cam-2025-p1-q1"
    assert chunk.sub_question_label == "a"
    assert chunk.marks == 10


def test_chunk_id_generation():
    from src.chunking.models import make_chunk_id

    assert make_chunk_id("cam", 2025, 1, 1) == "cam-2025-p1-q1"
    assert make_chunk_id("cam", 2025, 1, 1, "a") == "cam-2025-p1-q1-a"
    assert make_chunk_id("cam", 2025, 1, 1, "c") == "cam-2025-p1-q1-c"


def test_parsed_question_has_table_field():
    sq = SubQuestion(label="a", text="Some text.", marks=5)
    pq = ParsedQuestion(
        tripos_part="Part IA",
        year=2025,
        paper=1,
        question_number=3,
        topic="Databases",
        author="tgg22",
        preamble="Consider the following table...",
        sub_questions=[sq],
        total_marks=5,
        has_code=False,
        has_figure=False,
        has_table=True,
        warnings=[],
    )
    assert pq.has_table is True


def test_chunk_has_table_field():
    chunk = Chunk(
        id="cam-2025-p1-q2",
        chunk_level="question",
        parent_chunk_id=None,
        text="Consider the following relation...",
        year=2025,
        paper=1,
        question_number=2,
        topic="Databases",
        author="tgg22",
        tripos_part="Part IA",
        sub_question_label=None,
        marks=None,
        total_marks=20,
        has_code=False,
        has_figure=False,
        has_table=True,
        media=[],
        source_pdf="y2025p1q2.pdf",
        warnings=[],
    )
    assert chunk.has_table is True
