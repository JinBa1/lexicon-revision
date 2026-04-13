"""Infrastructure tests for inspect_chroma.py.

These tests use a disposable Chroma directory to verify CLI tooling behavior.
They do not test product search quality.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import chromadb
import pytest
from scripts.inspect_chroma import (
    build_collection_report,
    main,
    parse_args,
    render_json,
    render_text,
)


def _seed_chroma(chroma_dir: Path) -> str:
    collection_name = "tool-test-chroma"
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(collection_name)
    collection.upsert(
        ids=["chunk-1", "chunk-2"],
        documents=[
            "Binary search trees support lookup.",
            "Scheduling policies trade off latency and fairness.",
        ],
        embeddings=[[1.0, 0.0], [0.0, 1.0]],
        metadatas=[
            {
                "year": 2025,
                "paper": 1,
                "question_number": 1,
                "topic": "Algorithms",
                "chunk_level": "question",
                "source_pdf": "y2025p1q1.pdf",
            },
            {
                "year": 2024,
                "paper": 1,
                "question_number": 2,
                "topic": "Operating Systems",
                "chunk_level": "question",
                "source_pdf": "y2024p1q2.pdf",
            },
        ],
    )
    sidecar = chroma_dir / f"{collection_name}_media_map.json"
    sidecar.write_text(
        json.dumps(
            {
                "chunk-1": [
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "file_path": "fig.png",
                        "relation": "direct",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return collection_name


def test_build_collection_report_includes_count_and_records(
    tmp_path: Path,
) -> None:
    """Infrastructure test for Chroma storage inspection only."""
    collection_name = _seed_chroma(tmp_path)

    report = build_collection_report(
        chroma_dir=str(tmp_path),
        collection_name=collection_name,
        peek=2,
        chunk_id=None,
        limit=10,
        show_media=True,
        max_text_chars=80,
    )

    assert report["collection"] == collection_name
    assert report["count"] == 2
    assert report["media_entry_count"] == 1
    assert report["sidecar_path"].endswith(f"{collection_name}_media_map.json")
    assert len(report["records"]) == 2
    assert report["records"][0]["id"] in {"chunk-1", "chunk-2"}


def test_render_text_includes_metadata_and_preview(tmp_path: Path) -> None:
    """Infrastructure test for human-readable Chroma output only."""
    collection_name = _seed_chroma(tmp_path)
    report = build_collection_report(
        chroma_dir=str(tmp_path),
        collection_name=collection_name,
        peek=1,
        chunk_id="chunk-1",
        limit=10,
        show_media=True,
        max_text_chars=80,
    )

    output = render_text(report)

    assert f"Collection: {collection_name}" in output
    assert "Count: 2" in output
    assert "chunk-1" in output
    assert "topic=Algorithms" in output
    assert "media=1" in output
    assert "Binary search trees support lookup." in output


def test_render_json_is_parseable_and_stable(tmp_path: Path) -> None:
    """Infrastructure test for machine-readable Chroma output only."""
    collection_name = _seed_chroma(tmp_path)
    report = build_collection_report(
        chroma_dir=str(tmp_path),
        collection_name=collection_name,
        peek=1,
        chunk_id="chunk-1",
        limit=10,
        show_media=False,
        max_text_chars=80,
    )

    payload_first = render_json(report)
    parsed = json.loads(payload_first)

    assert parsed["collection"] == collection_name
    assert parsed["sidecar_path"].endswith(f"{collection_name}_media_map.json")
    assert set(parsed) == {
        "chroma_dir",
        "collection",
        "count",
        "media_entry_count",
        "records",
        "sidecar_path",
    }
    assert parsed["records"][0] == {
        "document_preview": "Binary search trees support lookup.",
        "id": "chunk-1",
        "media_count": 1,
        "metadata": {
            "chunk_level": "question",
            "paper": 1,
            "question_number": 1,
            "source_pdf": "y2025p1q1.pdf",
            "topic": "Algorithms",
            "year": 2025,
        },
    }


def test_cli_list_collections_prints_seeded_collection_name(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    """Infrastructure test for inspect_chroma CLI argument handling only."""
    collection_name = _seed_chroma(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_chroma.py", "--chroma-dir", str(tmp_path), "--list-collections"],
    )

    main()

    assert collection_name in capsys.readouterr().out


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--peek", "-1"),
        ("--limit", "-1"),
        ("--max-text-chars", "-1"),
    ],
)
def test_parse_args_rejects_non_positive_integers(
    monkeypatch,
    capsys,
    flag: str,
    value: str,
) -> None:
    """Infrastructure test for CLI argument validation only."""
    monkeypatch.setattr(
        sys,
        "argv",
        ["inspect_chroma.py", flag, value],
    )

    with pytest.raises(SystemExit) as excinfo:
        parse_args()

    assert excinfo.value.code == 2
    assert "positive integer" in capsys.readouterr().err


def test_main_reports_missing_collection_without_traceback(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    """Infrastructure test for CLI error handling only."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inspect_chroma.py",
            "--chroma-dir",
            str(tmp_path),
            "--collection",
            "missing",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "Collection 'missing' not found." in err
    assert "Use --list-collections to inspect available collections." in err
