"""A/B retrieval comparison: raw query vs planner-rewritten query."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inspect_search import (  # noqa: E402
    build_provider_metadata,
    create_real_search_service,
)
from src.search.models import SearchResponse  # noqa: E402
from src.search.service import DEFAULT_CHROMA_DIR  # noqa: E402
from src.study.config import load_study_settings  # noqa: E402
from src.study.planning.models import StudyFilters  # noqa: E402
from src.study.planning.planner import LLMQueryPlanner, QueryPlanner  # noqa: E402
from src.study.planning.retrieval import PlannedRetrievalService  # noqa: E402
from src.study.providers.ollama import OllamaProvider  # noqa: E402

_PLANNER_ERRORS = (Exception,)


@dataclass(frozen=True)
class MessyVariant:
    id: str
    query: str


@dataclass(frozen=True)
class MessyCase:
    id: str
    filters: dict[str, Any]
    any_chunk_ids: list[str]
    any_topics: list[str]
    variants: list[MessyVariant]


@dataclass(frozen=True)
class MessyEvalSpec:
    name: str
    collection: str | None
    default_top_k: int
    cases: list[MessyCase]


def load_messy_eval_spec(path: Path) -> MessyEvalSpec:
    """Load planner A/B eval YAML."""
    loaded = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a YAML mapping")

    cases: list[MessyCase] = []
    for entry in loaded.get("cases", []):
        variants = [
            MessyVariant(id=variant["id"], query=variant["query"])
            for variant in entry.get("variants", [])
        ]
        if not variants and "query" in entry:
            variants = [MessyVariant(id="default", query=entry["query"])]

        expected = entry.get("expected") or {}
        cases.append(
            MessyCase(
                id=entry["id"],
                filters=dict(entry.get("filters") or {}),
                any_chunk_ids=list(expected.get("any_chunk_ids") or []),
                any_topics=list(expected.get("any_topics") or []),
                variants=variants,
            )
        )

    return MessyEvalSpec(
        name=loaded["name"],
        collection=loaded.get("collection"),
        default_top_k=int(loaded.get("default_top_k", 15)),
        cases=cases,
    )


async def compare_cases(
    *,
    spec: MessyEvalSpec,
    collection: str,
    top_k: int,
    planner: QueryPlanner,
    search_service: Any,
    rerank: bool = False,
) -> dict[str, Any]:
    """Compare raw retrieval with planner-rewritten retrieval."""
    case_reports: list[dict[str, Any]] = []
    fallback_count = 0
    total_variants = 0
    planned_retrieval = PlannedRetrievalService(search_service=search_service)

    for case in spec.cases:
        filters_model = _parse_filters(case.filters)
        filters_dict = (
            filters_model.model_dump(exclude_none=True)
            if filters_model is not None
            else None
        )

        for variant in case.variants:
            total_variants += 1
            raw_response = search_service.search(
                query=variant.query,
                collection=collection,
                filters=filters_dict,
                limit=top_k,
                rerank=rerank,
            )
            raw_hit = _hit(raw_response, case)

            planning_status = "ok"
            planning_error: str | None = None
            planned_query = variant.query
            try:
                plan = await planner.plan(variant.query, filters_model)
                planned_result = planned_retrieval.retrieve(
                    plan,
                    hard_filters=filters_model,
                    collection=collection,
                    limit=top_k,
                    rerank=rerank,
                )
                planned_response = planned_result.search_response
                planned_query = planned_result.executed_queries[0]
            except _PLANNER_ERRORS as exc:
                planning_status = "fallback"
                planning_error = type(exc).__name__
                fallback_count += 1
                planned_response = search_service.search(
                    query=planned_query,
                    collection=collection,
                    filters=filters_dict,
                    limit=top_k,
                    rerank=rerank,
                )
            planned_hit = _hit(planned_response, case)

            case_reports.append(
                {
                    "id": f"{case.id}/{variant.id}",
                    "filters": case.filters,
                    "expected": {
                        "any_chunk_ids": case.any_chunk_ids,
                        "any_topics": case.any_topics,
                    },
                    "raw": {
                        "query": variant.query,
                        "hit": raw_hit,
                        "top_ids": [
                            result.chunk_id for result in raw_response.results[:top_k]
                        ],
                    },
                    "planned": {
                        "query": planned_query,
                        "hit": planned_hit,
                        "planning_status": planning_status,
                        "planning_error": planning_error,
                        "top_ids": [
                            result.chunk_id
                            for result in planned_response.results[:top_k]
                        ],
                    },
                }
            )

    hit_delta_sum = sum(
        (1 if case["planned"]["hit"] else 0) - (1 if case["raw"]["hit"] else 0)
        for case in case_reports
    )
    return {
        "name": spec.name,
        "collection": collection,
        "top_k": top_k,
        "providers": build_provider_metadata(search_service),
        "cases": case_reports,
        "aggregate": {
            "variant_count": total_variants,
            "fallback_rate": fallback_count / total_variants if total_variants else 0.0,
            "hit_delta_sum": hit_delta_sum,
        },
    }


def _hit(response: SearchResponse, case: MessyCase) -> bool:
    expected_ids = set(case.any_chunk_ids)
    expected_topics = set(case.any_topics)
    for result in response.results:
        if result.chunk_id in expected_ids:
            return True
        topic = result.metadata.get("topic")
        if isinstance(topic, str) and topic in expected_topics:
            return True
    return False


def _parse_filters(raw: dict[str, Any]) -> StudyFilters | None:
    if not raw:
        return None
    return StudyFilters.model_validate(raw)


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Planner A/B report: {report['name']}",
        f"collection={report['collection']} top_k={report['top_k']}",
        (
            f"variants={report['aggregate']['variant_count']} "
            f"fallback_rate={report['aggregate']['fallback_rate']:.2f} "
            f"hit_delta_sum={report['aggregate']['hit_delta_sum']}"
        ),
        "",
    ]
    for case in report["cases"]:
        lines.append(f"## {case['id']}")
        lines.append(f"raw hit={case['raw']['hit']} q={case['raw']['query']!r}")
        lines.append(
            f"planned hit={case['planned']['hit']} "
            f"status={case['planned']['planning_status']} "
            f"q={case['planned']['query']!r}"
        )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Planner A/B retrieval comparison")
    parser.add_argument("eval_path", type=Path)
    parser.add_argument("--collection", default=None)
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--chroma-dir", default=DEFAULT_CHROMA_DIR)
    parser.add_argument("--json", action="store_true")
    rerank_group = parser.add_mutually_exclusive_group()
    rerank_group.add_argument(
        "--rerank",
        dest="rerank",
        action="store_true",
        help="Apply cross-encoder reranking",
    )
    rerank_group.add_argument(
        "--no-rerank",
        dest="rerank",
        action="store_false",
        help="Disable cross-encoder reranking (default for planner A/B)",
    )
    parser.set_defaults(rerank=False)
    parser.add_argument(
        "--reranker-device",
        choices=["cpu", "cuda", "auto"],
        default="auto",
        help="Device for the cross-encoder reranker when --rerank is set",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    spec = load_messy_eval_spec(args.eval_path)
    collection = args.collection or spec.collection
    if collection is None:
        raise SystemExit("collection must be set via --collection or YAML")
    top_k = args.top_k or spec.default_top_k

    settings = load_study_settings()
    search_service = create_real_search_service(
        args.chroma_dir,
        rerank=args.rerank,
        reranker_device=args.reranker_device,
    )
    provider = OllamaProvider(
        base_url=settings.generation.base_url,
        model=settings.generation.model,
        max_retries=settings.generation.max_provider_retries,
    )
    planner = LLMQueryPlanner(provider=provider, settings=settings.planning)
    try:
        report = await compare_cases(
            spec=spec,
            collection=collection,
            top_k=top_k,
            planner=planner,
            search_service=search_service,
            rerank=args.rerank,
        )
    finally:
        await provider.aclose()

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_report(report))


def main() -> None:
    asyncio.run(_run(parse_args()))


if __name__ == "__main__":
    main()
