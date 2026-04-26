from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from scripts.verify_render_blocks import _shape_failures
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "verify_render_blocks.py"


@dataclass(frozen=True)
class SeededCollection:
    name: str


def test_verify_render_blocks_script_exists() -> None:
    assert SCRIPT.exists()


def test_script_passes_for_well_formed_collection(
    seeded_collection_with_blocks: SeededCollection,
) -> None:
    result = _run_script(seeded_collection_with_blocks.name)

    assert result.returncode == 0, result.stderr
    assert "chunks total: 1" in result.stdout


def test_script_fails_when_chunk_has_text_but_no_blocks(
    seeded_collection_with_legacy_chunk: SeededCollection,
) -> None:
    result = _run_script(seeded_collection_with_legacy_chunk.name)

    assert result.returncode == 1
    assert "render_blocks" in (result.stderr + result.stdout).lower()


def test_shape_failures_rejects_invalid_render_block_schema() -> None:
    failures = _shape_failures(
        "bad-1",
        [
            {
                "type": "paragraph",
                "runs": [{"type": "text", "text": "ok", "unexpected": True}],
            }
        ],
    )

    assert failures
    assert "schema validation failed" in failures[0]


def test_script_fails_for_invalid_render_block_schema(
    seeded_collection_with_invalid_blocks: SeededCollection,
) -> None:
    result = _run_script(seeded_collection_with_invalid_blocks.name)

    assert result.returncode == 1
    assert "schema validation failed" in (result.stderr + result.stdout)


@pytest.fixture
def pg_engine() -> Engine:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("TEST_DATABASE_URL is required for verify_render_blocks tests")

    engine = create_engine(database_url, future=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def seeded_collection_with_blocks(pg_engine: Engine) -> SeededCollection:
    name = f"verify-render-blocks-ok-{uuid.uuid4()}"
    _seed_collection(
        pg_engine,
        name=name,
        chunk_id="ok-1",
        text_value="Question with blocks",
        render_blocks=[
            {
                "type": "paragraph",
                "runs": [{"type": "text", "text": "Question with blocks"}],
            },
            {"type": "image", "media_id": "image_1"},
            {"type": "table", "rows": [["a", "b"]], "media_id": "table_1"},
        ],
    )
    return SeededCollection(name=name)


@pytest.fixture
def seeded_collection_with_legacy_chunk(pg_engine: Engine) -> SeededCollection:
    name = f"verify-render-blocks-legacy-{uuid.uuid4()}"
    _seed_collection(
        pg_engine,
        name=name,
        chunk_id="legacy-1",
        text_value="Legacy text without render blocks",
        render_blocks=None,
    )
    return SeededCollection(name=name)


@pytest.fixture
def seeded_collection_with_invalid_blocks(pg_engine: Engine) -> SeededCollection:
    name = f"verify-render-blocks-invalid-{uuid.uuid4()}"
    _seed_collection(
        pg_engine,
        name=name,
        chunk_id="invalid-1",
        text_value="Invalid render blocks",
        render_blocks=[
            {
                "type": "paragraph",
                "runs": [{"type": "text", "text": "Invalid", "extra": "bad"}],
            }
        ],
    )
    return SeededCollection(name=name)


def _run_script(collection_name: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    database_url = env["TEST_DATABASE_URL"]
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--collection",
            collection_name,
            "--database-url",
            database_url,
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _seed_collection(
    engine: Engine,
    *,
    name: str,
    chunk_id: str,
    text_value: str,
    render_blocks: list[dict[str, object]] | None,
) -> None:
    collection_id = str(uuid.uuid4())
    paper_id = str(uuid.uuid4())
    row_id = str(uuid.uuid4())
    metadata_schema = {
        "version": 1,
        "fields": [
            {"key": "year", "label": "Year", "type": "integer", "operators": ["eq"]}
        ],
    }

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO collections (
                    id,
                    name,
                    community_id,
                    embedding_model_id,
                    embedding_dimension,
                    metadata_schema
                )
                VALUES (
                    :collection_id,
                    :name,
                    NULL,
                    'test-model',
                    3,
                    CAST(:metadata_schema AS JSONB)
                )
                """
            ),
            {
                "collection_id": collection_id,
                "name": name,
                "metadata_schema": json.dumps(metadata_schema),
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO papers (id, collection_id, source_pdf)
                VALUES (:paper_id, :collection_id, 'verify.pdf')
                """
            ),
            {"paper_id": paper_id, "collection_id": collection_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO chunks (
                    id,
                    chunk_id,
                    collection_id,
                    paper_id,
                    chunk_level,
                    parent_chunk_id,
                    sub_question_label,
                    text,
                    metadata,
                    render_blocks,
                    source_pdf
                )
                VALUES (
                    :row_id,
                    :chunk_id,
                    :collection_id,
                    :paper_id,
                    'question',
                    NULL,
                    NULL,
                    :text_value,
                    '{}'::jsonb,
                    CAST(:render_blocks AS JSONB),
                    'verify.pdf'
                )
                """
            ),
            {
                "row_id": row_id,
                "chunk_id": chunk_id,
                "collection_id": collection_id,
                "paper_id": paper_id,
                "text_value": text_value,
                "render_blocks": (
                    json.dumps(render_blocks) if render_blocks is not None else None
                ),
            },
        )
