from pathlib import Path

from src.chunking.models import Chunk
from src.chunking.pipeline import run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
MINERU_FIXTURES = str(REPO_ROOT / "tests" / "data" / "mineru_fixtures")
METADATA_PATH = str(REPO_ROOT / "data" / "papers" / "metadata.json")


def test_pipeline_produces_chunks():
    """Run pipeline on MinerU fixtures and verify chunk output."""
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        metadata_path=METADATA_PATH,
        university="cam",
    )
    assert len(chunks) > 0
    assert all(isinstance(c, Chunk) for c in chunks)


def test_pipeline_chunk_ids_are_unique():
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        metadata_path=METADATA_PATH,
        university="cam",
    )
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk IDs found"


def test_pipeline_question_chunks_have_children():
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        metadata_path=METADATA_PATH,
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


def test_pipeline_merges_downloader_metadata():
    """Chunks should pick up topic and author from metadata.json."""
    chunks = run_pipeline(
        mineru_output_dir=MINERU_FIXTURES,
        metadata_path=METADATA_PATH,
        university="cam",
    )
    q1_chunks = [
        c for c in chunks if c.question_number == 1 and c.chunk_level == "question"
    ]
    # Find a 2025 q1 chunk
    q1 = next((c for c in q1_chunks if c.year == 2025), None)
    assert q1 is not None
    assert q1.topic == "Foundations of Computer Science"
    assert q1.author == "avsm2"


def test_pipeline_no_metadata_file(tmp_path):
    """Pipeline should work without metadata.json — metadata fields from parser only."""
    import shutil

    src = Path(MINERU_FIXTURES) / "y2025p1q1"
    dst = tmp_path / "y2025p1q1"
    shutil.copytree(src, dst)

    chunks = run_pipeline(
        mineru_output_dir=str(tmp_path),
        metadata_path=str(tmp_path / "metadata.json"),
        university="cam",
    )
    assert len(chunks) > 0
    q = [c for c in chunks if c.chunk_level == "question"][0]
    assert q.tripos_part == "Part IA"
    assert q.year == 2025
