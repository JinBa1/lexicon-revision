"""Infrastructure tests for evaluate_study.py.

These tests exercise batch-study evaluation plumbing only. They do not measure
model quality, real retrieval quality, or real Ollama behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from scripts.evaluate_study import (
    evaluate_study_cases,
    load_study_eval_spec,
    render_json,
    render_markdown,
)
from src.study.models import (
    GenerationMetadata,
    RetrievalMetadata,
    StudyAnswer,
    StudyRequest,
    StudyResponse,
    StudyScope,
    StudySource,
)


class ToolTestFakeStudyService:
    """Recording study service for batch evaluation tests."""

    def __init__(self, responses: dict[str, StudyResponse]) -> None:
        self.responses = responses
        self.calls: list[StudyRequest] = []

    async def orchestrate(self, request: StudyRequest) -> StudyResponse:
        self.calls.append(request)
        return self.responses[request.query]


def _response(
    *,
    query: str,
    collection: str,
    answer_status: str = "ok",
    context_chunk_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
) -> StudyResponse:
    context_chunk_ids = context_chunk_ids or ["chunk-1"]
    source_ids = source_ids or ["chunk-1"]
    return StudyResponse(
        request_id=f"request-{query}",
        query=query,
        scope=StudyScope(collection=collection),
        answer_status=answer_status,  # type: ignore[arg-type]
        answer=StudyAnswer(
            overview=f"Overview for {query}.",
            patterns=[],
            limitations=["Limited fixture evidence."],
        ),
        sources=[
            StudySource(
                chunk_id=chunk_id,
                year=2025,
                paper=1,
                question_ref="Q1",
                chunk_level="question",
                topic="Algorithms",
                score=0.91,
                excerpt=f"{chunk_id} excerpt text",
                why_cited="Relevant source.",
            )
            for chunk_id in source_ids
        ],
        retrieval=RetrievalMetadata(
            status="ok",
            top_k=15,
            returned_result_count=len(context_chunk_ids),
            context_budget_tokens=4000,
            context_chunk_ids=context_chunk_ids,
            omitted_chunk_ids=[],
            truncated_chunk_ids=[],
            filters_applied={},
            rerank=True,
        ),
        generation=GenerationMetadata(
            provider="ollama",
            model="qwen2.5:7b-instruct",
            prompt_version="study_aid_v1",
            temperature=0.1,
            attempt_count=1,
            citation_drops=0,
            error_category=None,
            latency_ms=12,
        ),
    )


def test_load_study_eval_spec_accepts_authored_variants(tmp_path: Path) -> None:
    """Variant text is authored input and preserved exactly."""
    eval_path = tmp_path / "study_eval.yaml"
    eval_path.write_text(
        """
name: study_probe
collection: cam-cs-tripos-fixture
default_top_k: 12
cases:
  - id: broad-dp
    purpose: Probe direct-topic versus method-required wording.
    filters:
      paper: 1
    expected:
      any_chunk_ids:
        - cam-2024-p1-q7-e
      any_topics:
        - Algorithms 2
    variants:
      - id: on
        query: past questions on dynamic programming and greedy algorithms
      - id: requires
        query: past questions requiring dynamic programming and greedy algorithms
""",
        encoding="utf-8",
    )

    spec = load_study_eval_spec(eval_path)

    assert spec.name == "study_probe"
    assert spec.collection == "cam-cs-tripos-fixture"
    assert spec.default_top_k == 12
    assert spec.cases[0].filters == {"paper": 1}
    assert spec.cases[0].any_chunk_ids == ["cam-2024-p1-q7-e"]
    assert [variant.id for variant in spec.cases[0].variants] == ["on", "requires"]
    assert spec.cases[0].variants[1].query == (
        "past questions requiring dynamic programming and greedy algorithms"
    )


def test_load_study_eval_spec_preserves_boolean_filters_and_on_variant_id(
    tmp_path: Path,
) -> None:
    """YAML true/false remain booleans while variant id 'on' remains a string."""
    eval_path = tmp_path / "study_eval.yaml"
    eval_path.write_text(
        """
name: study_probe
collection: cam-cs-tripos-fixture
cases:
  - id: surface-code-oop
    filters:
      has_code: true
    expected:
      any_chunk_ids:
        - cam-2024-p1-q4
    variants:
      - id: on
        query: past questions on OOP code
""",
        encoding="utf-8",
    )

    spec = load_study_eval_spec(eval_path)

    assert spec.cases[0].filters == {"has_code": True}
    assert spec.cases[0].variants[0].id == "on"


def test_load_study_eval_spec_treats_search_eval_query_as_default_variant(
    tmp_path: Path,
) -> None:
    """Existing search eval YAML can be used without adding variants first."""
    eval_path = tmp_path / "search_eval.yaml"
    eval_path.write_text(
        """
name: search_style
collection: cam-cs-tripos-fixture
cases:
  - id: concept-vm
    query: memory management and virtual memory paging
    expected:
      any_chunk_ids:
        - cam-2025-p2-q4
""",
        encoding="utf-8",
    )

    spec = load_study_eval_spec(eval_path)

    assert spec.cases[0].variants[0].id == "default"
    assert spec.cases[0].variants[0].query == (
        "memory management and virtual memory paging"
    )
    assert spec.cases[0].any_chunk_ids == ["cam-2025-p2-q4"]


def test_load_study_eval_spec_rejects_string_boolean_filter(tmp_path: Path) -> None:
    """Quoted boolean filters are rejected before they can cause empty retrieval."""
    eval_path = tmp_path / "study_eval.yaml"
    eval_path.write_text(
        """
name: study_probe
collection: cam-cs-tripos-fixture
cases:
  - id: bad-filter
    query: class hierarchy code example
    filters:
      has_code: "true"
    expected:
      any_chunk_ids:
        - cam-2024-p1-q4
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="has_code.*boolean"):
        load_study_eval_spec(eval_path)


def test_evaluate_study_cases_runs_each_variant_with_same_scope(
    tmp_path: Path,
) -> None:
    """Batch runner calls StudyService once per authored variant."""
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "study_probe",
                "collection": collection,
                "default_top_k": 9,
                "cases": [
                    {
                        "id": "broad-dp",
                        "filters": {"paper": 1},
                        "expected": {"any_chunk_ids": ["chunk-1"]},
                        "variants": [
                            {"id": "on", "query": "questions on dp"},
                            {"id": "requires", "query": "questions requiring dp"},
                        ],
                    }
                ],
            },
        )
    )
    service = ToolTestFakeStudyService(
        {
            "questions on dp": _response(
                query="questions on dp",
                collection=collection,
                context_chunk_ids=["chunk-1", "chunk-2"],
            ),
            "questions requiring dp": _response(
                query="questions requiring dp",
                collection=collection,
                context_chunk_ids=["chunk-3"],
                source_ids=["chunk-3"],
            ),
        }
    )

    report = evaluate_study_cases(
        service=service,  # type: ignore[arg-type]
        spec=spec,
        collection=collection,
        top_k=9,
        case_ids=None,
        variant_ids=None,
    )

    assert [call.query for call in service.calls] == [
        "questions on dp",
        "questions requiring dp",
    ]
    assert all(call.scope.collection == collection for call in service.calls)
    assert all(call.filters == {"paper": 1} for call in service.calls)
    assert all(call.top_k == 9 for call in service.calls)
    first = report["cases"][0]["variants"][0]
    assert first["retrieval"]["expected_in_context"] is True
    assert first["retrieval"]["context_chunk_ids"] == ["chunk-1", "chunk-2"]
    assert report["case_count"] == 1
    assert report["variant_count"] == 2


def test_render_outputs_group_variants_for_review(tmp_path: Path) -> None:
    """Rendered artifacts are stable enough for human or agent review."""
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "study_probe",
                "collection": collection,
                "cases": [
                    {
                        "id": "concept-vm",
                        "purpose": "Probe fine-grained virtual memory wording.",
                        "expected": {
                            "any_chunk_ids": ["chunk-1"],
                            "any_topics": ["Operating Systems"],
                        },
                        "variants": [
                            {
                                "id": "pte",
                                "query": "page table PTE questions",
                            }
                        ],
                    }
                ],
            },
        )
    )
    service = ToolTestFakeStudyService(
        {
            "page table PTE questions": _response(
                query="page table PTE questions",
                collection=collection,
                answer_status="partial",
            )
        }
    )
    report = evaluate_study_cases(
        service=service,  # type: ignore[arg-type]
        spec=spec,
        collection=collection,
        top_k=15,
        case_ids=None,
        variant_ids=None,
    )

    parsed = json.loads(render_json(report))
    markdown = render_markdown(report, max_text_chars=80)

    assert parsed["name"] == "study_probe"
    assert parsed["cases"][0]["variants"][0]["query"] == "page table PTE questions"
    assert "# Study Eval: study_probe" in markdown
    assert "## concept-vm" in markdown
    assert "### pte" in markdown
    assert "Answer status: `partial`" in markdown
    assert "Context chunk IDs: `chunk-1`" in markdown
    assert "Overview for page table PTE questions." in markdown


def test_render_markdown_accepts_inspect_study_generation_shape() -> None:
    """Real inspect_study payloads store citation drops under validation."""
    report = {
        "name": "study_probe",
        "description": None,
        "collection": "cam-cs-tripos-fixture",
        "top_k": 15,
        "case_count": 1,
        "variant_count": 1,
        "cases": [
            {
                "id": "case-1",
                "purpose": None,
                "filters": {},
                "expected": {"any_chunk_ids": [], "any_topics": []},
                "variants": [
                    {
                        "id": "default",
                        "query": "page table PTE questions",
                        "retrieval": {
                            "status": "ok",
                            "returned_result_count": 3,
                            "context_chunk_ids": ["chunk-1"],
                            "expected_in_context": False,
                        },
                        "generation": {
                            "provider": "ollama",
                            "model": "qwen2.5:7b-instruct",
                            "attempt_count": 1,
                            "error_category": None,
                            "latency_ms": 12,
                        },
                        "validation": {
                            "answer_status": "partial",
                            "citation_drops": 2,
                            "cited_source_ids": ["chunk-1"],
                        },
                        "answer": {
                            "overview": "One relevant page-table source was found.",
                            "patterns": [],
                            "limitations": [],
                        },
                        "sources": [],
                    }
                ],
            }
        ],
    }

    markdown = render_markdown(report, max_text_chars=80)

    assert "citation drops `2`" in markdown
    assert "error `none`" in markdown


def _write_eval(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "study-eval.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
