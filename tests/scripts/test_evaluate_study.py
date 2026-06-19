"""Infrastructure tests for evaluate_study.py.

These tests exercise batch-study evaluation plumbing only. They do not measure
model quality, real retrieval quality, or real Ollama behavior.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts.evaluate_study import (
    evaluate_study_cases,
    load_study_eval_spec,
    parse_args,
    render_json,
    render_markdown,
)
from src.metadata_schema.models import FilterCondition
from src.study.models import (
    GenerationMetadata,
    RetrievalMetadata,
    StudyAnswer,
    StudyRequest,
    StudyResponse,
    StudyScope,
    StudySource,
)
from src.study.planning.models import PlanningMetadata


class ToolTestFakeStudyService:
    """Recording study service for batch evaluation tests."""

    def __init__(self, responses: dict[str, StudyResponse]) -> None:
        self.responses = responses
        self.calls: list[StudyRequest] = []

    async def orchestrate(self, request: StudyRequest) -> StudyResponse:
        self.calls.append(request)
        return self.responses[request.query]


def test_parse_args_accepts_no_planning(tmp_path: Path, monkeypatch) -> None:
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text("name: x\ncases: []\n", encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_study.py", str(eval_path), "--no-planning"],
    )

    args = parse_args()

    assert args.no_planning is True


def test_parse_args_rerank_defaults_and_flags(tmp_path: Path, monkeypatch) -> None:
    eval_path = tmp_path / "eval.yaml"
    eval_path.write_text("name: x\ncases: []\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["evaluate_study.py", str(eval_path)])
    assert parse_args().rerank is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_study.py",
            str(eval_path),
            "--no-rerank",
            "--reranker-device",
            "cpu",
        ],
    )
    args = parse_args()
    assert args.rerank is False
    assert args.reranker_device == "cpu"


def _response(
    *,
    query: str,
    collection: str,
    answer_status: str = "ok",
    context_chunk_ids: list[str] | None = None,
    source_ids: list[str] | None = None,
    planning: PlanningMetadata | None = None,
    retrieval_status: str = "ok",
    reflection_graded: bool = False,
    requery_attempted: bool = False,
    graded_chunk_count: int = 0,
) -> StudyResponse:
    context_chunk_ids = ["chunk-1"] if context_chunk_ids is None else context_chunk_ids
    source_ids = ["chunk-1"] if source_ids is None else source_ids
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
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                score=0.91,
                excerpt=f"{chunk_id} excerpt text",
                metadata={
                    "year": 2025,
                    "paper": 1,
                    "question_number": 1,
                    "topic": "Algorithms",
                },
                why_cited="Relevant source.",
            )
            for chunk_id in source_ids
        ],
        retrieval=RetrievalMetadata(
            status=retrieval_status,  # type: ignore[arg-type]
            top_k=15,
            returned_result_count=len(context_chunk_ids),
            context_budget_tokens=4000,
            context_chunk_ids=context_chunk_ids,
            omitted_chunk_ids=[],
            truncated_chunk_ids=[],
            filters_applied=[],
            rerank=True,
            reflection_graded=reflection_graded,
            requery_attempted=requery_attempted,
            graded_chunk_count=graded_chunk_count,
        ),
        planning=planning
        or PlanningMetadata(
            status="ok",
            planner_version="query_planner_v1",
            original_query=query,
            semantic_queries=[query],
            latency_ms=5,
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
      - field: paper
        op: eq
        value: 1
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
    assert spec.cases[0].filters == [FilterCondition(field="paper", op="eq", value=1)]
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
      - field: has_code
        op: eq
        value: true
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

    assert spec.cases[0].filters == [
        FilterCondition(field="has_code", op="eq", value=True)
    ]
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


def test_load_study_eval_spec_preserves_string_scalar_filter_values(
    tmp_path: Path,
) -> None:
    """Study eval tooling preserves authored scalar values without schema typing."""
    eval_path = tmp_path / "study_eval.yaml"
    eval_path.write_text(
        """
name: study_probe
collection: cam-cs-tripos-fixture
cases:
  - id: bad-filter
    query: class hierarchy code example
    filters:
      - field: has_code
        op: eq
        value: "true"
    expected:
      any_chunk_ids:
        - cam-2024-p1-q4
""",
        encoding="utf-8",
    )

    spec = load_study_eval_spec(eval_path)

    assert spec.cases[0].filters == [
        FilterCondition(field="has_code", op="eq", value="true")
    ]


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
                        "filters": [
                            {
                                "field": "paper",
                                "op": "eq",
                                "value": 1,
                            }
                        ],
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
    assert all(
        (call.filters or []) == [FilterCondition(field="paper", op="eq", value=1)]
        for call in service.calls
    )
    assert all(call.top_k == 9 for call in service.calls)
    first = report["cases"][0]["variants"][0]
    assert first["retrieval"]["expected_in_context"] is True
    assert first["retrieval"]["context_chunk_ids"] == ["chunk-1", "chunk-2"]
    assert report["case_count"] == 1
    assert report["variant_count"] == 2


def test_report_includes_planning_per_variant(tmp_path: Path) -> None:
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "study_probe",
                "collection": collection,
                "cases": [
                    {
                        "id": "broad-dp",
                        "query": "questions on dp",
                        "expected": {"any_chunk_ids": ["chunk-1"]},
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
                planning=PlanningMetadata(
                    status="fallback",
                    planner_version="query_planner_v1",
                    original_query="questions on dp",
                    semantic_queries=["questions on dp"],
                    error_category="provider_timeout",
                    latency_ms=100,
                ),
            )
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

    variant = report["cases"][0]["variants"][0]
    assert "planning" in variant
    assert variant["planning"]["status"] == "fallback"
    assert variant["planning"]["error_category"] == "provider_timeout"
    assert variant["planning"]["planner_version"] == "query_planner_v1"
    assert variant["planning"]["original_query"] == "questions on dp"
    assert variant["planning"]["latency_ms"] == 100
    assert variant["planning"]["semantic_queries"] == ["questions on dp"]
    assert report["planner_fallback_rate"] == 1.0


def test_render_markdown_includes_semantic_queries_in_planning_summary(
    tmp_path: Path,
) -> None:
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "study_probe",
                "collection": collection,
                "cases": [
                    {
                        "id": "broad-dp",
                        "query": "questions on dp",
                        "expected": {"any_chunk_ids": ["chunk-1"]},
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
                planning=PlanningMetadata(
                    status="ok",
                    planner_version="query_planner_v1",
                    original_query="questions on dp",
                    semantic_queries=["dynamic programming recurrence"],
                    latency_ms=20,
                ),
            )
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

    rendered = render_markdown(report)

    assert "semantic_queries=`['dynamic programming recurrence']`" in rendered


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
                "filters": [],
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


def test_reflection_aggregates_recall_and_non_regression(tmp_path: Path) -> None:
    """A negative case that abstains + a content case that hits drive PR3 metrics."""
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "reflection_probe",
                "collection": collection,
                "default_top_k": 9,
                "cases": [
                    {
                        "id": "off-topic",
                        "expected": {
                            "any_chunk_ids": [],
                            "expected_answer_status": "insufficient_evidence",
                        },
                        "variants": [{"id": "v", "query": "capital of France"}],
                    },
                    {
                        "id": "content",
                        "expected": {"any_chunk_ids": ["chunk-1"]},
                        "variants": [{"id": "v", "query": "dp recurrences"}],
                    },
                ],
            },
        )
    )
    service = ToolTestFakeStudyService(
        {
            "capital of France": _response(
                query="capital of France",
                collection=collection,
                answer_status="insufficient_evidence",
                retrieval_status="low_relevance",
                reflection_graded=True,
                requery_attempted=True,
                context_chunk_ids=[],
                source_ids=[],
            ),
            "dp recurrences": _response(
                query="dp recurrences",
                collection=collection,
                context_chunk_ids=["chunk-1"],
                source_ids=["chunk-1"],
                reflection_graded=True,
                graded_chunk_count=1,
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

    assert report["abstain_recall"] == 1.0
    assert report["abstain_false_positive_rate"] == 0.0
    assert report["non_regression_content_hit_rate"] == 1.0
    assert report["requery_rate"] == 0.5
    assert report["negative_requery_attempts"] == 1


def test_reflection_false_abstain_counted_against_content_case(tmp_path: Path) -> None:
    """A content case wrongly abstained (low_relevance) raises the FP rate."""
    collection = "cam-cs-tripos-fixture"
    spec = load_study_eval_spec(
        _write_eval(
            tmp_path,
            {
                "name": "reflection_fp",
                "collection": collection,
                "default_top_k": 9,
                "cases": [
                    {
                        "id": "content",
                        "expected": {"any_chunk_ids": ["chunk-1"]},
                        "variants": [{"id": "v", "query": "dp recurrences"}],
                    }
                ],
            },
        )
    )
    service = ToolTestFakeStudyService(
        {
            "dp recurrences": _response(
                query="dp recurrences",
                collection=collection,
                answer_status="insufficient_evidence",
                retrieval_status="low_relevance",
                reflection_graded=True,
                context_chunk_ids=[],
                source_ids=[],
            )
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

    assert report["abstain_false_positive_rate"] == 1.0
    assert report["non_regression_content_hit_rate"] == 0.0
    assert report["abstain_recall"] is None  # no negative cases


def _write_eval(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "study-eval.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path
