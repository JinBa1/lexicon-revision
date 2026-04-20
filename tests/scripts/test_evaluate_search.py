"""Infrastructure tests for evaluate_search.py.

These tests exercise the CLI plumbing only. They do not measure product search
quality, real embeddings, or real reranking.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from scripts.evaluate_search import (
    evaluate_cases,
    main,
    parse_args,
    render_json,
    render_text,
)
from scripts.search_tooling import EvalCase, load_eval_spec
from src.metadata_schema.models import FilterCondition
from src.search.errors import CollectionNotFoundError
from src.search.models import SearchResponse, SearchResult


class ToolTestFakeSearchService:
    """Recording search service for CLI evaluation and rendering tests."""

    embedding_model_id = "tool-test-embedding"
    rerank_model_id = None

    def __init__(self, responses: dict[str, SearchResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    def search(
        self,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = False,
    ) -> SearchResponse:
        self.calls.append(
            {
                "query": query,
                "collection": collection,
                "filters": filters,
                "limit": limit,
                "rerank": rerank,
            }
        )
        return self.responses[query]


class ToolTestMissingCollectionService:
    """Search service stub that always raises a collection lookup error."""

    def search(
        self,
        query: str,
        collection: str,
        filters: list[FilterCondition] | None = None,
        limit: int = 10,
        rerank: bool = False,
    ) -> SearchResponse:
        raise CollectionNotFoundError(collection)


def _result(*, chunk_id: str, topic: str, score: float) -> SearchResult:
    return SearchResult(
        chunk_id=chunk_id,
        chunk_level="question",
        parent_chunk_id=None,
        sub_question_label=None,
        text=f"{chunk_id} body text",
        score=score,
        metadata={
            "year": 2025,
            "paper": 1,
            "question_number": 1,
            "topic": topic,
            "author": None,
            "tripos_part": None,
            "chunk_level": "question",
            "parent_chunk_id": None,
            "sub_question_label": None,
            "marks": None,
            "total_marks": 20,
            "has_code": False,
            "has_figure": False,
            "has_table": False,
            "source_pdf": "y2025p1q1.pdf",
        },
        media=[],
    )


def _response(
    query: str, collection: str, results: list[SearchResult]
) -> SearchResponse:
    return SearchResponse(
        query=query, collection=collection, total=len(results), results=results
    )


def test_parse_args_rejects_non_positive_limit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Infrastructure test for CLI argument validation only."""
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            "eval.yaml",
            "--limit",
            "0",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        parse_args()

    assert excinfo.value.code == 2
    assert "positive integer" in capsys.readouterr().err


def test_main_uses_eval_spec_default_top_k_as_limit_when_not_specified(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Infrastructure test: --limit defaults to eval file default_top_k when omitted."""
    query = "binary search trees"
    collection = "tool-test-collection"
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
collection: tool-test-collection
default_top_k: 7
cases:
  - id: case-1
    query: binary search trees
    expected:
      any_chunk_ids:
        - chunk-1
""",
        encoding="utf-8",
    )
    service = ToolTestFakeSearchService(
        {
            query: _response(
                query,
                collection,
                [_result(chunk_id="chunk-1", topic="Algorithms", score=0.95)],
            )
        }
    )
    monkeypatch.setattr(
        "scripts.evaluate_search.create_real_search_service",
        lambda chroma_dir, rerank: service,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_search.py", str(eval_path)],
    )

    main()

    # effective_limit = max(limit=7, 10, max_top_k=7) → 10; the raw limit passed
    # into evaluate_cases must be 7 (from eval file default_top_k)
    assert service.calls[0]["limit"] >= 7


def test_evaluate_cases_passes_on_expected_chunk_id_within_top_k() -> None:
    """Infrastructure test for search evaluation matching only."""
    query = "binary search trees"
    collection = "tool-test-collection"
    response = _response(
        query,
        collection,
        [
            _result(chunk_id="chunk-1", topic="Algorithms", score=0.91),
            _result(chunk_id="chunk-2", topic="Data Structures", score=0.88),
            _result(chunk_id="chunk-3", topic="Theory", score=0.54),
        ],
    )
    service = ToolTestFakeSearchService({query: response})

    report = evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=[
            EvalCase(
                id="chunk-id-match",
                query=query,
                filters=[],
                any_chunk_ids=["chunk-2"],
                any_topics=[],
                top_k=3,
                notes="should match chunk-2",
            )
        ],
        collection=collection,
        limit=5,
        rerank=False,
        name="search_eval",
    )

    assert service.calls[0]["collection"] == collection
    assert report["providers"] == {
        "embedding_model_id": "tool-test-embedding",
        "rerank_model_id": None,
    }
    assert report["passed_count"] == 1
    assert report["metrics"] == {
        "hit_at_1": 0,
        "hit_at_3": 1,
        "hit_at_5": 1,
        "hit_at_10": 1,
    }
    assert report["cases"][0]["passed"] is True
    assert report["cases"][0]["matched_rank"] == 2


def test_evaluate_cases_passes_on_expected_topic_within_top_k() -> None:
    """Infrastructure test for search evaluation matching only."""
    query = "algorithm practice"
    collection = "tool-test-collection"
    response = _response(
        query,
        collection,
        [
            _result(chunk_id="chunk-1", topic="Algorithms", score=0.95),
            _result(chunk_id="chunk-2", topic="Theory", score=0.73),
        ],
    )
    service = ToolTestFakeSearchService({query: response})

    report = evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=[
            EvalCase(
                id="topic-match",
                query=query,
                filters=[],
                any_chunk_ids=[],
                any_topics=["Algorithms"],
                top_k=1,
                notes=None,
            )
        ],
        collection=collection,
        limit=5,
        rerank=False,
        name="search_eval",
    )

    assert report["cases"][0]["passed"] is True
    assert report["cases"][0]["matched_rank"] == 1
    assert report["metrics"]["hit_at_1"] == 1


def test_evaluate_cases_fails_when_no_expectation_appears() -> None:
    """Infrastructure test for search evaluation matching only."""
    query = "graph traversal"
    collection = "tool-test-collection"
    response = _response(
        query,
        collection,
        [
            _result(chunk_id="chunk-1", topic="Algorithms", score=0.91),
            _result(chunk_id="chunk-2", topic="Theory", score=0.74),
        ],
    )
    service = ToolTestFakeSearchService({query: response})

    report = evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=[
            EvalCase(
                id="no-match",
                query=query,
                filters=[],
                any_chunk_ids=["chunk-9"],
                any_topics=["Databases"],
                top_k=2,
                notes="expected to fail",
            )
        ],
        collection=collection,
        limit=5,
        rerank=False,
        name="search_eval",
    )

    assert report["cases"][0]["passed"] is False
    assert report["cases"][0]["matched_rank"] is None
    assert report["metrics"] == {
        "hit_at_1": 0,
        "hit_at_3": 0,
        "hit_at_5": 0,
        "hit_at_10": 0,
    }


def test_load_eval_spec_accepts_filter_condition_list(
    tmp_path: Path,
) -> None:
    """Infrastructure test for eval filter plumbing only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
collection: tool-test-collection
cases:
  - id: case-1
    query: binary search trees
    filters:
      - field: question_number
        op: eq
        value: 3
      - field: paper
        op: eq
        value: 1
    expected:
      any_chunk_ids:
        - chunk-1
""",
        encoding="utf-8",
    )

    spec = load_eval_spec(eval_path)
    query = "binary search trees"
    collection = "tool-test-collection"
    service = ToolTestFakeSearchService(
        {
            query: _response(
                query,
                collection,
                [_result(chunk_id="chunk-1", topic="Algorithms", score=0.95)],
            )
        }
    )

    evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=spec.cases,
        collection=collection,
        limit=5,
        rerank=False,
        name=spec.name,
    )

    assert service.calls[0]["filters"] == [
        FilterCondition(field="question_number", op="eq", value=3),
        FilterCondition(field="paper", op="eq", value=1),
    ]


def test_render_text_includes_metrics_and_failures() -> None:
    """Infrastructure test for readable CLI output only."""
    pass_query = "binary search trees"
    fail_query = "graph traversal"
    collection = "tool-test-collection"
    service = ToolTestFakeSearchService(
        {
            pass_query: _response(
                pass_query,
                collection,
                [_result(chunk_id="chunk-1", topic="Algorithms", score=0.91)],
            ),
            fail_query: _response(
                fail_query,
                collection,
                [
                    _result(chunk_id="chunk-2", topic="Theory", score=0.74),
                    _result(chunk_id="chunk-3", topic="Databases", score=0.68),
                ],
            ),
        }
    )

    report = evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=[
            EvalCase(
                id="pass-case",
                query=pass_query,
                filters=[],
                any_chunk_ids=["chunk-1"],
                any_topics=[],
                top_k=1,
                notes=None,
            ),
            EvalCase(
                id="fail-case",
                query=fail_query,
                filters=[],
                any_chunk_ids=["chunk-9"],
                any_topics=["Algorithms"],
                top_k=2,
                notes="expected to fail",
            ),
        ],
        collection=collection,
        limit=5,
        rerank=False,
        name="search_eval",
    )

    output = render_text(report)

    assert "Passed: 1/2" in output
    assert "Hit@1:" in output
    assert "Hit@3:" in output
    assert "Failures" in output
    assert "fail-case" in output
    assert "No expected chunk ID or topic appeared within top_k results." in output


def test_render_json_is_parseable() -> None:
    """Infrastructure test for machine-readable CLI output only."""
    query = "binary search trees"
    collection = "tool-test-collection"
    service = ToolTestFakeSearchService(
        {
            query: _response(
                query,
                collection,
                [_result(chunk_id="chunk-1", topic="Algorithms", score=0.95)],
            )
        }
    )

    report = evaluate_cases(
        service=service,  # type: ignore[arg-type]
        cases=[
            EvalCase(
                id="json-case",
                query=query,
                filters=[],
                any_chunk_ids=["chunk-1"],
                any_topics=[],
                top_k=1,
                notes=None,
            )
        ],
        collection=collection,
        limit=5,
        rerank=False,
        name="search_eval",
    )

    parsed = json.loads(render_json(report))

    assert parsed["name"] == "search_eval"
    assert parsed["providers"]["embedding_model_id"] == "tool-test-embedding"
    assert parsed["cases"][0]["id"] == "json-case"


def test_main_reports_missing_collection_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Infrastructure test for CLI error handling only."""
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text(
        """
name: tool_test
cases:
  - id: case-1
    query: binary search trees
    expected:
      any_chunk_ids:
        - chunk-1
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.evaluate_search.create_real_search_service",
        lambda chroma_dir, rerank: ToolTestMissingCollectionService(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            str(eval_path),
            "--collection",
            "missing",
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert "Collection 'missing' not found." in err


def test_main_exits_nonzero_after_printing_and_writing_failed_report(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Infrastructure test for CLI failure exit status only."""
    eval_path = tmp_path / "eval.yaml"
    output_path = tmp_path / "report.json"
    query = "graph traversal"
    collection = "tool-test-collection"
    eval_path.write_text(
        """
name: tool_test
collection: tool-test-collection
cases:
  - id: case-1
    query: graph traversal
    expected:
      any_chunk_ids:
        - chunk-9
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.evaluate_search.create_real_search_service",
        lambda chroma_dir, rerank: ToolTestFakeSearchService(
            {
                query: _response(
                    query,
                    collection,
                    [
                        _result(
                            chunk_id="chunk-1",
                            topic="Algorithms",
                            score=0.91,
                        )
                    ],
                )
            }
        ),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            str(eval_path),
            "--output",
            str(output_path),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    stdout = capsys.readouterr().out
    assert "Passed: 0/1" in stdout
    assert "FAIL" in stdout
    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["failed_count"] == 1


def test_main_reports_output_write_failure_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    """Infrastructure test for CLI write error handling only."""
    eval_path = tmp_path / "eval.yaml"
    output_path = tmp_path / "report.json"
    query = "binary search trees"
    collection = "tool-test-collection"
    eval_path.write_text(
        """
name: tool_test
collection: tool-test-collection
cases:
  - id: case-1
    query: binary search trees
    expected:
      any_chunk_ids:
        - chunk-1
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.evaluate_search.create_real_search_service",
        lambda chroma_dir, rerank: ToolTestFakeSearchService(
            {
                query: _response(
                    query,
                    collection,
                    [_result(chunk_id="chunk-1", topic="Algorithms", score=0.95)],
                )
            }
        ),
    )
    monkeypatch.setattr(
        "scripts.evaluate_search.Path.write_text",
        lambda self, data, encoding=None: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_search.py",
            str(eval_path),
            "--output",
            str(output_path),
        ],
    )

    with pytest.raises(SystemExit) as excinfo:
        main()

    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    stdout = captured.out
    stderr = captured.err
    assert "Passed: 1/1" in stdout
    assert "Error writing report to" in stderr
