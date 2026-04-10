"""Integration tests for `run_pipeline`.

These tests exercise the MinerU-fixture -> parser -> chunk assembly path.
Passing them means the current fixture corpus is parsed into structurally valid
chunks, metadata is merged correctly, and the current media ownership semantics
behave as expected on the covered cases.

Passing this file still does NOT prove the pipeline works well on all Cambridge
papers or even all fixture shapes the project may encounter later. This is a
regression suite over selected cases, not a corpus-wide correctness guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.chunking.models import Chunk, ParsedMediaBlock, ParsedQuestion, SubQuestion
from src.chunking.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")


def _media_refs(chunk: Chunk) -> list:
    return list(chunk.media)


def _fixture_media_path(stem: str, media_type: str) -> str:
    return str(Path(_fixture_media_block(stem, media_type)["resolved_img_path"]))


def _fixture_media_block(stem: str, media_type: str) -> dict:
    content_list_path = (
        REPO_ROOT
        / "tests"
        / "data"
        / "mineru_fixtures"
        / stem
        / "hybrid_auto"
        / f"{stem}_content_list.json"
    )
    blocks = json.loads(content_list_path.read_text(encoding="utf-8"))
    media_blocks = [block for block in blocks if block.get("type") == media_type]
    assert len(media_blocks) == 1
    media_block = dict(media_blocks[0])
    media_block["resolved_img_path"] = (
        content_list_path.parent / media_block["img_path"]
    )
    return media_block


def test_pipeline_produces_chunks():
    """The pipeline returns Chunk objects for the committed MinerU fixtures."""
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )
    assert len(chunks) > 0
    assert all(isinstance(c, Chunk) for c in chunks)


def test_pipeline_chunk_ids_are_unique():
    """Chunk ID generation stays collision-free across the current fixture set."""
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"


def test_pipeline_question_chunks_have_children():
    """Every sub-question chunk points to an existing question-level parent."""
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )
    question_chunks = [c for c in chunks if c.chunk_level == "question"]
    sub_chunks = [c for c in chunks if c.chunk_level == "sub_question"]

    assert len(question_chunks) > 0
    assert len(sub_chunks) > 0

    question_ids = {c.id for c in question_chunks}
    for sub in sub_chunks:
        assert sub.parent_chunk_id in question_ids, (
            f"Sub-chunk {sub.id} references non-existent parent {sub.parent_chunk_id}"
        )


def test_pipeline_merges_downloader_metadata(tmp_path):
    """Downloader metadata takes precedence over parser-extracted topic/author."""
    import shutil

    src = Path(MINERU_FIXTURES) / "y2025p1q1"
    dst = tmp_path / "y2025p1q1"
    shutil.copytree(src, dst)

    metadata = {
        "y2025p1q1.pdf": {
            "year": 2025,
            "paper": 1,
            "question": 1,
            "topic": "Overridden Topic",
            "author": "override_author",
        }
    }
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    chunks = run_pipeline(
        mineru_output_dir=str(tmp_path),
        metadata_path=str(metadata_path),
        university="cam",
    )
    q1 = next(c for c in chunks if c.chunk_level == "question")
    assert q1.topic == "Overridden Topic"
    assert q1.author == "override_author"


def test_pipeline_table_media_uses_child_visibility_semantics():
    """A table local to part `(b)` is direct on `b` and visible on the question."""
    table_image_path = _fixture_media_path("y2018p8q7", "table")
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )

    question = next(c for c in chunks if c.id == "cam-2018-p8-q7")
    sub_a = next(c for c in chunks if c.id == "cam-2018-p8-q7-a")
    sub_b = next(c for c in chunks if c.id == "cam-2018-p8-q7-b")

    question_table_refs = [
        ref for ref in _media_refs(question) if ref.file_path == table_image_path
    ]
    sub_a_table_refs = [
        ref for ref in _media_refs(sub_a) if ref.file_path == table_image_path
    ]
    sub_b_table_refs = [
        ref for ref in _media_refs(sub_b) if ref.file_path == table_image_path
    ]

    assert len(question_table_refs) == 1
    assert len(sub_b_table_refs) == 1
    assert len(sub_a_table_refs) == 0

    question_ref = question_table_refs[0]
    sub_b_ref = sub_b_table_refs[0]

    assert getattr(question_ref, "relation", None) == "visible_from_child"
    assert getattr(sub_b_ref, "relation", None) == "direct"
    assert getattr(sub_b_ref, "owner_level", None) == "sub_question"
    assert getattr(sub_b_ref, "owner_label", None) == "b"


def test_pipeline_table_media_preserves_page_number_and_bbox_from_mineru():
    """Attached media keeps real MinerU location metadata instead of placeholders."""
    media_block = _fixture_media_block("y2018p8q7", "table")
    table_image_path = str(Path(media_block["resolved_img_path"]).resolve())
    expected_bbox = tuple(float(value) for value in media_block["bbox"])
    expected_page_number = media_block["page_idx"] + 1

    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )

    question = next(c for c in chunks if c.id == "cam-2018-p8-q7")
    table_ref = next(
        ref for ref in _media_refs(question) if ref.file_path == table_image_path
    )

    assert table_ref.page_number == expected_page_number
    assert table_ref.page_number == 1
    assert table_ref.bbox == expected_bbox
    assert table_ref.bbox is not None


def test_pipeline_unmatched_owner_hint_stays_question_only(monkeypatch, tmp_path):
    """Unknown owner hints must not leak media onto unrelated sub-question chunks."""
    content_list_path = tmp_path / "synthetic_content_list.json"
    content_list_path.write_text("[]", encoding="utf-8")

    parsed_question = ParsedQuestion(
        tripos_part="Part IA",
        year=2025,
        paper=1,
        question_number=9,
        topic=None,
        author=None,
        preamble="Question preamble.",
        sub_questions=[
            SubQuestion(label="a", text="Part a"),
            SubQuestion(label="b", text="Part b"),
        ],
        total_marks=None,
        has_code=False,
        has_figure=True,
        has_table=False,
        media_blocks=[
            ParsedMediaBlock(
                media_id="image_0",
                kind="image",
                file_path="images/orphan.png",
                page_number=2,
                bbox=(1.0, 2.0, 3.0, 4.0),
                order_index=0,
                owner_hint_label="z",
                is_shared_candidate=False,
            )
        ],
    )

    def fake_parse(_self: object, _path: str) -> list[ParsedQuestion]:
        return [parsed_question]

    monkeypatch.setattr(
        "src.chunking.pipeline.CambridgeContentListParser.parse",
        fake_parse,
    )

    chunks = run_pipeline(
        mineru_output_dir=str(tmp_path),
        metadata_path=str(tmp_path / "metadata.json"),
        university="cam",
    )

    question = next(c for c in chunks if c.id == "cam-2025-p1-q9")
    sub_a = next(c for c in chunks if c.id == "cam-2025-p1-q9-a")
    sub_b = next(c for c in chunks if c.id == "cam-2025-p1-q9-b")

    assert len(_media_refs(question)) == 1
    assert len(_media_refs(sub_a)) == 0
    assert len(_media_refs(sub_b)) == 0

    question_ref = _media_refs(question)[0]
    assert question_ref.relation == "direct"
    assert question_ref.owner_level == "question"
    assert question_ref.owner_label is None


def test_pipeline_shared_media_is_visible_from_question_and_children():
    """Preamble/shared media is direct on the question and inherited by children."""
    image_path = _fixture_media_path("y2018p1q4", "image")
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        university="cam",
    )

    question = next(c for c in chunks if c.id == "cam-2018-p1-q4")
    sub_a = next(c for c in chunks if c.id == "cam-2018-p1-q4-a")
    sub_b = next(c for c in chunks if c.id == "cam-2018-p1-q4-b")

    question_media_refs = [
        ref for ref in _media_refs(question) if ref.file_path == image_path
    ]
    sub_a_media_refs = [
        ref for ref in _media_refs(sub_a) if ref.file_path == image_path
    ]
    sub_b_media_refs = [
        ref for ref in _media_refs(sub_b) if ref.file_path == image_path
    ]

    assert len(question_media_refs) == 1
    assert len(sub_a_media_refs) == 1
    assert len(sub_b_media_refs) == 1

    assert getattr(question_media_refs[0], "relation", None) == "direct"
    assert getattr(sub_a_media_refs[0], "relation", None) == "inherited_shared"
    assert getattr(sub_b_media_refs[0], "relation", None) == "inherited_shared"
