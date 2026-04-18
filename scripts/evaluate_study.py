"""Run authored study query variants in batch and collect review evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Allow direct execution via `python scripts/evaluate_study.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inspect_search import create_real_search_service  # noqa: E402
from scripts.inspect_study import RecordingProvider, build_payload  # noqa: E402
from scripts.search_tooling import SUPPORTED_FILTER_KEYS, truncate_text  # noqa: E402
from src.search.service import DEFAULT_CHROMA_DIR, CollectionNotFoundError  # noqa: E402
from src.study.config import load_study_settings  # noqa: E402
from src.study.models import StudyRequest, StudyScope  # noqa: E402
from src.study.planning.planner import LLMQueryPlanner, RawQueryPlanner  # noqa: E402
from src.study.planning.retrieval import PlannedRetrievalService  # noqa: E402
from src.study.providers.ollama import OllamaProvider  # noqa: E402
from src.study.service import StudyService  # noqa: E402


@dataclass(frozen=True)
class StudyVariant:
    id: str
    query: str


@dataclass(frozen=True)
class StudyEvalCase:
    id: str
    purpose: str | None
    filters: dict[str, Any]
    any_chunk_ids: list[str]
    any_topics: list[str]
    variants: list[StudyVariant]


@dataclass(frozen=True)
class StudyEvalSpec:
    name: str
    description: str | None
    collection: str | None
    default_top_k: int
    cases: list[StudyEvalCase]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the study batch runner."""
    parser = argparse.ArgumentParser(
        description="Run authored study query variants in batch",
    )
    parser.add_argument("eval_path", type=Path, help="Path to study eval YAML/JSON")
    parser.add_argument(
        "--chroma-dir",
        default=DEFAULT_CHROMA_DIR,
        help=f"ChromaDB storage directory (default: {DEFAULT_CHROMA_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Override the collection from the eval file",
    )
    parser.add_argument(
        "--top-k",
        type=_positive_int,
        default=None,
        help="Study retrieval top-k (default: eval default_top_k, or settings)",
    )
    parser.add_argument(
        "--case-id",
        action="append",
        dest="case_ids",
        help="Run only this case ID; repeat for multiple cases",
    )
    parser.add_argument(
        "--variant-id",
        action="append",
        dest="variant_ids",
        help="Run only this variant ID; repeat for multiple variants",
    )
    parser.add_argument(
        "--settings",
        type=Path,
        default=None,
        help="Optional path to an alternate study settings YAML directory",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format printed to stdout",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the full JSON report to this path",
    )
    parser.add_argument(
        "--review-output",
        type=Path,
        help="Write the Markdown review report to this path",
    )
    parser.add_argument(
        "--max-text-chars",
        type=_positive_int,
        default=500,
        help="Preview length for answer/source excerpts in Markdown",
    )
    parser.add_argument(
        "--no-planning",
        action="store_true",
        help="Bypass LLM query planning and retrieve with each raw query",
    )
    rerank_group = parser.add_mutually_exclusive_group()
    rerank_group.add_argument(
        "--rerank",
        dest="rerank",
        action="store_true",
        help="Apply cross-encoder reranking (default)",
    )
    rerank_group.add_argument(
        "--no-rerank",
        dest="rerank",
        action="store_false",
        help="Disable cross-encoder reranking (avoid GPU contention with Ollama)",
    )
    parser.set_defaults(rerank=True)
    parser.add_argument(
        "--reranker-device",
        choices=["cpu", "cuda", "auto"],
        default="auto",
        help="Device for the cross-encoder reranker (default: auto)",
    )
    return parser.parse_args()


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def load_study_eval_spec(path: str | Path) -> StudyEvalSpec:
    """Load authored study variants from YAML or JSON."""
    eval_path = Path(path)
    payload = yaml.load(eval_path.read_text(encoding="utf-8"), Loader=_StudyEvalLoader)
    if not isinstance(payload, dict):
        raise ValueError("Study eval file must contain a mapping at the top level")

    name = _required_string(payload.get("name"), "name")
    default_top_k = payload.get("default_top_k", 15)
    if type(default_top_k) is not int or default_top_k <= 0:
        raise ValueError("default_top_k must be a positive integer")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Study eval file requires non-empty list field 'cases'")

    return StudyEvalSpec(
        name=name,
        description=_optional_string(payload.get("description"), "description"),
        collection=_optional_string(payload.get("collection"), "collection"),
        default_top_k=default_top_k,
        cases=[_parse_case(raw_case) for raw_case in raw_cases],
    )


class _StudyEvalLoader(yaml.SafeLoader):
    """Safe YAML loader that does not treat words like "on" as booleans."""


_StudyEvalLoader.yaml_implicit_resolvers = deepcopy(
    yaml.SafeLoader.yaml_implicit_resolvers
)
for first_char, resolvers in list(_StudyEvalLoader.yaml_implicit_resolvers.items()):
    _StudyEvalLoader.yaml_implicit_resolvers[first_char] = [
        (tag, regexp) for tag, regexp in resolvers if tag != "tag:yaml.org,2002:bool"
    ]
_StudyEvalLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"),
)


def _parse_case(raw_case: Any) -> StudyEvalCase:
    if not isinstance(raw_case, dict):
        raise ValueError("Each study eval case must be a mapping")

    case_id = _required_string(raw_case.get("id"), "case id")
    filters = _parse_filters(case_id, raw_case.get("filters") or {})
    expected = raw_case.get("expected") or {}
    if not isinstance(expected, dict):
        raise ValueError(f"Study eval case '{case_id}' expected must be a mapping")

    variants = _parse_variants(case_id, raw_case)
    return StudyEvalCase(
        id=case_id,
        purpose=_optional_string(raw_case.get("purpose"), f"case '{case_id}' purpose"),
        filters=filters,
        any_chunk_ids=_parse_string_list(
            expected.get("any_chunk_ids"),
            f"case '{case_id}' expected.any_chunk_ids",
        ),
        any_topics=_parse_string_list(
            expected.get("any_topics"),
            f"case '{case_id}' expected.any_topics",
        ),
        variants=variants,
    )


def _parse_variants(case_id: str, raw_case: dict[str, Any]) -> list[StudyVariant]:
    raw_variants = raw_case.get("variants")
    if raw_variants is None:
        query = _required_string(raw_case.get("query"), f"case '{case_id}' query")
        return [StudyVariant(id="default", query=query)]

    if not isinstance(raw_variants, list) or not raw_variants:
        raise ValueError(f"Study eval case '{case_id}' variants must be a list")

    variants: list[StudyVariant] = []
    seen_ids: set[str] = set()
    for raw_variant in raw_variants:
        if not isinstance(raw_variant, dict):
            raise ValueError(f"Study eval case '{case_id}' variants must be mappings")
        variant_id = _required_string(raw_variant.get("id"), "variant id")
        if variant_id in seen_ids:
            raise ValueError(
                f"Study eval case '{case_id}' has duplicate variant id '{variant_id}'"
            )
        seen_ids.add(variant_id)
        variants.append(
            StudyVariant(
                id=variant_id,
                query=_required_string(raw_variant.get("query"), "variant query"),
            )
        )
    return variants


def _parse_filters(case_id: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Study eval case '{case_id}' filters must be a mapping")
    unknown_filters = set(value) - (SUPPORTED_FILTER_KEYS | {"question"})
    if unknown_filters:
        unknown = ", ".join(sorted(unknown_filters))
        raise ValueError(
            f"Study eval case '{case_id}' has unsupported filters: {unknown}"
        )

    parsed: dict[str, Any] = {}
    for key, raw_value in value.items():
        normalized = "question_number" if key == "question" else key
        if normalized in {"year", "paper", "question_number", "marks_min"}:
            if type(raw_value) is not int:
                raise ValueError(
                    f"Study eval case '{case_id}' filter '{normalized}' must be "
                    "an integer"
                )
        elif normalized in {"has_code", "has_figure", "has_table"}:
            if type(raw_value) is not bool:
                raise ValueError(
                    f"Study eval case '{case_id}' filter '{normalized}' must be "
                    "a boolean"
                )
        elif normalized == "topic":
            if type(raw_value) is not str or not raw_value:
                raise ValueError(
                    f"Study eval case '{case_id}' filter '{normalized}' must be "
                    "a non-empty string"
                )
        parsed[normalized] = raw_value
    return parsed


def _parse_string_list(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    return value


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"Study eval requires non-empty string field '{field_name}'")
    return value


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Study eval field '{field_name}' must be a non-empty string")
    return value


def evaluate_study_cases(
    *,
    service: Any,
    spec: StudyEvalSpec,
    collection: str,
    top_k: int,
    case_ids: set[str] | None,
    variant_ids: set[str] | None,
) -> dict[str, Any]:
    """Run selected study variants and return a review-oriented report."""
    if top_k <= 0:
        raise ValueError("top_k must be positive")

    selected_cases = [
        case for case in spec.cases if case_ids is None or case.id in case_ids
    ]
    case_reports = [
        asyncio.run(_evaluate_case(service, case, collection, top_k, variant_ids))
        for case in selected_cases
    ]
    variants = [v for c in case_reports for v in c["variants"]]
    variant_count = len(variants)
    fallbacks = [
        v for v in variants if v.get("planning", {}).get("status") == "fallback"
    ]

    return {
        "name": spec.name,
        "description": spec.description,
        "collection": collection,
        "top_k": top_k,
        "case_count": len(case_reports),
        "variant_count": variant_count,
        "planner_fallback_rate": (
            len(fallbacks) / variant_count if variant_count > 0 else 0
        ),
        "cases": case_reports,
    }


async def _evaluate_case(
    service: Any,
    case: StudyEvalCase,
    collection: str,
    top_k: int,
    variant_ids: set[str] | None,
) -> dict[str, Any]:
    variants = [
        variant
        for variant in case.variants
        if variant_ids is None or variant.id in variant_ids
    ]
    variant_reports = [
        await _evaluate_variant(service, case, variant, collection, top_k)
        for variant in variants
    ]
    return {
        "id": case.id,
        "purpose": case.purpose,
        "filters": case.filters,
        "expected": {
            "any_chunk_ids": case.any_chunk_ids,
            "any_topics": case.any_topics,
        },
        "variants": variant_reports,
    }


async def _evaluate_variant(
    service: Any,
    case: StudyEvalCase,
    variant: StudyVariant,
    collection: str,
    top_k: int,
) -> dict[str, Any]:
    request = StudyRequest(
        query=variant.query,
        scope=StudyScope(collection=collection),
        filters=case.filters or None,
        top_k=top_k,
    )
    response = await service.orchestrate(request)
    response_dump = response.model_dump()
    context_chunk_ids = response.retrieval.context_chunk_ids
    source_chunk_ids = [source.chunk_id for source in response.sources]
    source_topics = [source.topic for source in response.sources if source.topic]

    return {
        "id": variant.id,
        "query": variant.query,
        "retrieval": {
            "status": response.retrieval.status,
            "returned_result_count": response.retrieval.returned_result_count,
            "context_chunk_ids": context_chunk_ids,
            "omitted_chunk_ids": response.retrieval.omitted_chunk_ids,
            "truncated_chunk_ids": response.retrieval.truncated_chunk_ids,
            "expected_in_context": _any_expected_chunk(
                context_chunk_ids, case.any_chunk_ids
            ),
        },
        "planning": {
            "status": response.planning.status,
            "error_category": response.planning.error_category,
            "planner_version": response.planning.planner_version,
            "original_query": response.planning.original_query,
            "latency_ms": response.planning.latency_ms,
            "semantic_queries": list(response.planning.semantic_queries),
        },
        "generation": {
            "provider": response.generation.provider,
            "model": response.generation.model,
            "attempt_count": response.generation.attempt_count,
            "citation_drops": response.generation.citation_drops,
            "error_category": response.generation.error_category,
            "latency_ms": response.generation.latency_ms,
        },
        "validation": {
            "answer_status": response.answer_status,
            "citation_drops": response.generation.citation_drops,
            "cited_source_ids": source_chunk_ids,
            "expected_in_sources": _any_expected_chunk(
                source_chunk_ids, case.any_chunk_ids
            ),
            "expected_topic_in_sources": bool(
                set(case.any_topics) & set(source_topics)
            ),
        },
        "answer": response_dump["answer"],
        "sources": response_dump["sources"],
        "response": response_dump,
    }


def _any_expected_chunk(actual_ids: list[str], expected_ids: list[str]) -> bool:
    if not expected_ids:
        return False
    return bool(set(actual_ids) & set(expected_ids))


def render_json(report: dict[str, Any]) -> str:
    """Render the full report as stable JSON."""
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)


def render_markdown(report: dict[str, Any], *, max_text_chars: int = 500) -> str:
    """Render a compact review report grouped by case and variant."""
    lines = [
        f"# Study Eval: {report['name']}",
        "",
        f"- Collection: `{report['collection']}`",
        f"- Top-k: `{report['top_k']}`",
        f"- Cases: `{report['case_count']}`",
        f"- Variants: `{report['variant_count']}`",
    ]
    if report.get("description"):
        lines.extend(["", report["description"]])

    for case in report["cases"]:
        lines.extend(["", f"## {case['id']}"])
        if case.get("purpose"):
            lines.append(case["purpose"])
        lines.append(f"- Filters: `{_format_mapping(case['filters'])}`")
        expected = case["expected"]
        lines.append(
            "- Expected chunks: "
            f"`{_format_list(expected['any_chunk_ids'])}`; "
            f"topics: `{_format_list(expected['any_topics'])}`"
        )
        for variant in case["variants"]:
            retrieval = variant["retrieval"]
            planning = variant.get("planning")
            generation = variant["generation"]
            validation = variant["validation"]
            answer = variant["answer"]
            lines.extend(
                [
                    "",
                    f"### {variant['id']}",
                    f"Query: `{variant['query']}`",
                ]
            )
            if planning:
                lines.append(
                    f"Planning: `{planning['status']}`; "
                    f"error `{planning['error_category'] or 'none'}`; "
                    f"semantic_queries=`{planning['semantic_queries']}`; "
                    f"latency `{planning['latency_ms']}ms`"
                )
            lines.extend(
                [
                    (
                        f"Retrieval: `{retrieval['status']}`; "
                        f"returned `{retrieval['returned_result_count']}`; "
                        f"expected in context `{retrieval['expected_in_context']}`"
                    ),
                    (
                        "Context chunk IDs: "
                        f"`{_format_list(retrieval['context_chunk_ids'])}`"
                    ),
                    (
                        f"Answer status: `{validation['answer_status']}`; "
                        f"citation drops `{validation['citation_drops']}`; "
                        f"error `{generation['error_category'] or 'none'}`"
                    ),
                    (
                        "Cited source IDs: "
                        f"`{_format_list(validation['cited_source_ids'])}`"
                    ),
                    (
                        f"Generation: `{generation['provider']}` "
                        f"`{generation['model']}`; attempts "
                        f"`{generation['attempt_count']}`; latency "
                        f"`{generation['latency_ms']}ms`"
                    ),
                ]
            )
            overview = answer.get("overview")
            if overview:
                lines.extend(
                    ["", "**Overview**", truncate_text(overview, max_text_chars)]
                )
            limitations = answer.get("limitations") or []
            if limitations:
                lines.extend(["", "**Limitations**"])
                lines.extend(
                    f"- {truncate_text(item, max_text_chars)}" for item in limitations
                )
            if variant["sources"]:
                lines.extend(["", "**Sources**"])
                for source in variant["sources"]:
                    lines.append(
                        "- "
                        f"`{source['chunk_id']}` "
                        f"topic=`{source.get('topic')}` "
                        f"score=`{source['score']:.4f}` "
                        f"excerpt={truncate_text(source['excerpt'], max_text_chars)}"
                    )

    return "\n".join(lines)


def _format_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "none"
    return " ".join(f"{key}={value}" for key, value in mapping.items())


def _format_list(values: list[Any]) -> str:
    if not values:
        return "none"
    return ", ".join(str(value) for value in values)


async def _run_real_report(args: argparse.Namespace) -> dict[str, Any]:
    spec = load_study_eval_spec(args.eval_path)
    settings = (
        load_study_settings(args.settings)
        if args.settings is not None
        else load_study_settings()
    )
    collection = args.collection or spec.collection
    if not collection:
        raise ValueError("Collection must be provided by eval file or --collection")
    top_k = args.top_k or spec.default_top_k or settings.context.retrieval_top_k_default

    search_service = create_real_search_service(
        args.chroma_dir,
        rerank=args.rerank,
        reranker_device=args.reranker_device,
    )
    inner_provider = OllamaProvider(
        base_url=settings.generation.base_url,
        model=settings.generation.model,
        max_retries=settings.generation.max_provider_retries,
    )
    provider = RecordingProvider(inner=inner_provider)
    query_planner = (
        RawQueryPlanner()
        if args.no_planning
        else LLMQueryPlanner(provider=provider, settings=settings.planning)
    )
    planned_retrieval = PlannedRetrievalService(search_service=search_service)
    study_service = StudyService(
        query_planner=query_planner,
        planned_retrieval=planned_retrieval,
        provider=provider,
        settings=settings,
    )

    try:
        return await _evaluate_real_cases(
            study_service=study_service,
            provider=provider,
            spec=spec,
            collection=collection,
            top_k=top_k,
            case_ids=set(args.case_ids) if args.case_ids else None,
            variant_ids=set(args.variant_ids) if args.variant_ids else None,
            prompt_version=settings.prompt.version,
        )
    finally:
        await provider.aclose()


async def _evaluate_real_cases(
    *,
    study_service: StudyService,
    provider: RecordingProvider,
    spec: StudyEvalSpec,
    collection: str,
    top_k: int,
    case_ids: set[str] | None,
    variant_ids: set[str] | None,
    prompt_version: str,
) -> dict[str, Any]:
    case_reports = []
    for case in spec.cases:
        if case_ids is not None and case.id not in case_ids:
            continue
        variant_reports = []
        for variant in case.variants:
            if variant_ids is not None and variant.id not in variant_ids:
                continue
            before = len(provider.interactions)
            request = StudyRequest(
                query=variant.query,
                scope=StudyScope(collection=collection),
                filters=case.filters or None,
                top_k=top_k,
            )
            response = await study_service.orchestrate(request)
            interactions = provider.interactions[before:]
            payload = build_payload(
                query=variant.query,
                collection=collection,
                filters=case.filters,
                top_k=top_k,
                response=response,
                interactions=interactions,
                prompt_version=prompt_version,
            )
            variant_reports.append(
                {
                    "id": variant.id,
                    "query": variant.query,
                    "retrieval": {
                        **payload["retrieval"],
                        "expected_in_context": _any_expected_chunk(
                            payload["retrieval"]["context_chunk_ids"],
                            case.any_chunk_ids,
                        ),
                    },
                    "planning": {
                        "status": response.planning.status,
                        "error_category": response.planning.error_category,
                        "planner_version": response.planning.planner_version,
                        "original_query": response.planning.original_query,
                        "latency_ms": response.planning.latency_ms,
                        "semantic_queries": list(response.planning.semantic_queries),
                    },
                    "generation": payload["generation"],
                    "validation": {
                        **payload["validation"],
                        "cited_source_ids": [
                            source["chunk_id"] for source in payload["sources"]
                        ],
                        "expected_in_sources": _any_expected_chunk(
                            [source["chunk_id"] for source in payload["sources"]],
                            case.any_chunk_ids,
                        ),
                        "expected_topic_in_sources": bool(
                            set(case.any_topics)
                            & {
                                source.get("topic")
                                for source in payload["sources"]
                                if source.get("topic")
                            }
                        ),
                    },
                    "answer": payload["answer"],
                    "sources": payload["sources"],
                    "attempts": payload["generation"]["attempts"],
                    "prompt": payload["prompt"],
                    "response": payload["response"],
                }
            )
        case_reports.append(
            {
                "id": case.id,
                "purpose": case.purpose,
                "filters": case.filters,
                "expected": {
                    "any_chunk_ids": case.any_chunk_ids,
                    "any_topics": case.any_topics,
                },
                "variants": variant_reports,
            }
        )

    variants = [v for c in case_reports for v in c["variants"]]
    variant_count = len(variants)
    fallbacks = [
        v for v in variants if v.get("planning", {}).get("status") == "fallback"
    ]

    return {
        "name": spec.name,
        "description": spec.description,
        "collection": collection,
        "top_k": top_k,
        "case_count": len(case_reports),
        "variant_count": variant_count,
        "planner_fallback_rate": (
            len(fallbacks) / variant_count if variant_count > 0 else 0
        ),
        "cases": case_reports,
    }


def main() -> None:
    """Run the local study batch utility."""
    args = parse_args()
    try:
        report = asyncio.run(_run_real_report(args))
    except CollectionNotFoundError as exc:
        print(f"Collection '{exc.collection_name}' not found.", file=sys.stderr)
        raise SystemExit(1) from exc
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    json_report = render_json(report)
    markdown_report = render_markdown(report, max_text_chars=args.max_text_chars)

    try:
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json_report, encoding="utf-8")
        if args.review_output:
            args.review_output.parent.mkdir(parents=True, exist_ok=True)
            args.review_output.write_text(markdown_report, encoding="utf-8")
    except OSError as exc:
        print(f"Could not write report: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json_report if args.format == "json" else markdown_report)


if __name__ == "__main__":
    main()
