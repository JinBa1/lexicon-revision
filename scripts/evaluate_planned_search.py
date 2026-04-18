"""A/B retrieval comparison: raw query vs planner-rewritten query."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

import yaml

# Allow direct execution
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inspect_search import create_real_search_service  # noqa: E402
from src.search.models import SearchResponse  # noqa: E402
from src.search.service import DEFAULT_CHROMA_DIR  # noqa: E402
from src.study.config import load_study_settings  # noqa: E402
from src.study.planning.models import StudyFilters  # noqa: E402
from src.study.planning.planner import LLMQueryPlanner, QueryPlanner  # noqa: E402
from src.study.planning.retrieval import PlannedRetrievalService  # noqa: E402
from src.study.providers.ollama import OllamaProvider  # noqa: E402


def load_messy_eval_spec(path: Path) -> list[dict[str, Any]]:
    """Load messy evaluation cases from a YAML file."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases = []
    for raw_case in payload.get("cases", []):
        expected = raw_case.get("expected", {})
        any_chunk_ids = expected.get("any_chunk_ids", [])
        any_topics = expected.get("any_topics", [])

        variants = raw_case.get("variants", [])
        if variants:
            messy_variant = next(
                (v for v in variants if v["id"] == "messy"), variants[0]
            )
            query = messy_variant["query"]
        else:
            query = raw_case.get("query")

        cases.append(
            {
                "id": raw_case.get("id", "unknown"),
                "query": query,
                "expected_chunk_ids": any_chunk_ids,
                "expected_topics": any_topics,
                "filters": raw_case.get("filters", {}),
            }
        )
    return cases


async def compare_cases(
    cases: list[dict[str, Any]],
    search_service: Any,
    planner: QueryPlanner,
    collection: str,
    limit: int,
) -> list[dict[str, Any]]:
    """Run A/B comparison for each case: raw query vs planned query."""
    results = []
    retrieval_service = PlannedRetrievalService(search_service=search_service)

    for case in cases:
        query = case["query"]
        expected_ids = case["expected_chunk_ids"]
        expected_topics = case["expected_topics"]
        case_filters = (
            StudyFilters.model_validate(case["filters"]) if case["filters"] else None
        )

        # Baseline: raw query + filters
        baseline_resp = search_service.search(
            query=query,
            collection=collection,
            filters=case["filters"] or None,
            limit=limit,
        )
        baseline_hit = _check_hit(baseline_resp, expected_ids, expected_topics)

        # Planned: planner-rewritten + filters
        try:
            plan = await planner.plan(query, hard_filters=case_filters)
            planned_ret = retrieval_service.retrieve(
                plan=plan,
                hard_filters=case_filters,
                collection=collection,
                limit=limit,
            )
            planned_hit = _check_hit(
                planned_ret.search_response, expected_ids, expected_topics
            )
            status = "ok"
            planned_query = plan.semantic_queries[0]
        except Exception as exc:
            status = "fallback"
            planned_hit = baseline_hit
            planned_query = f"(fallback) {query}"
            print(
                f"Warning: planner failed for query '{query}': {exc}", file=sys.stderr
            )

        results.append(
            {
                "id": case["id"],
                "query": query,
                "planned_query": planned_query,
                "baseline_hit": baseline_hit,
                "planned_hit": planned_hit,
                "status": status,
            }
        )
    return results


def _check_hit(
    response: SearchResponse, expected_ids: list[str], expected_topics: list[str]
) -> bool:
    """Check if any of the expected chunk IDs or topics are in the results."""
    expected_ids_set = set(expected_ids)
    expected_topics_set = set(expected_topics)

    for result in response.results:
        if result.chunk_id in expected_ids_set:
            return True
        topic = result.metadata.get("topic")
        if topic and topic in expected_topics_set:
            return True
    return False


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="A/B evaluation of planned retrieval")
    parser.add_argument("eval_path", type=Path, help="Path to messy eval YAML")
    parser.add_argument("--collection", help="Chroma collection override")
    parser.add_argument("--limit", type=int, default=15, help="Search limit (hit@k)")
    parser.add_argument(
        "--chroma-dir", default=DEFAULT_CHROMA_DIR, help="Chroma directory"
    )
    return parser.parse_args()


async def main() -> None:
    """Main execution loop."""
    args = parse_args()
    if not args.eval_path.exists():
        print(f"Error: eval file not found at {args.eval_path}", file=sys.stderr)
        sys.exit(1)

    cases = load_messy_eval_spec(args.eval_path)

    # Setup services
    settings = load_study_settings()
    search_service = create_real_search_service(args.chroma_dir, rerank=True)
    provider = OllamaProvider(
        base_url=settings.generation.base_url,
        model=settings.generation.model,
    )
    planner = LLMQueryPlanner(provider, settings.planning)

    # Determine collection
    payload = yaml.safe_load(args.eval_path.read_text(encoding="utf-8"))
    collection = args.collection or payload.get("collection") or "cam-cs-tripos"

    print(
        f"Evaluating {len(cases)} cases against collection '{collection}' "
        f"(limit={args.limit})..."
    )
    results = await compare_cases(
        cases=cases,
        search_service=search_service,
        planner=planner,
        collection=collection,
        limit=args.limit,
    )

    # Report per-case
    print(f"{'ID':<40} | {'Baseline':<10} | {'Planned':<10} | {'Status':<10}")
    print("-" * 80)

    baseline_hits = 0
    planned_hits = 0
    fallbacks = 0

    for res in results:
        b_hit = "HIT" if res["baseline_hit"] else "MISS"
        p_hit = "HIT" if res["planned_hit"] else "MISS"
        print(f"{res['id']:<40} | {b_hit:<10} | {p_hit:<10} | {res['status']:<10}")

        if res["baseline_hit"]:
            baseline_hits += 1
        if res["planned_hit"]:
            planned_hits += 1
        if res["status"] == "fallback":
            fallbacks += 1

    baseline_rate = baseline_hits / len(cases)
    planned_rate = planned_hits / len(cases)
    fallback_rate = fallbacks / len(cases)

    print("-" * 80)
    print(f"Baseline total hits: {baseline_hits}/{len(cases)} ({baseline_rate:.1%})")
    print(f"Planned total hits:  {planned_hits}/{len(cases)} ({planned_rate:.1%})")
    print(f"Delta:               {planned_hits - baseline_hits:+d}")
    print(f"Fallback rate:       {fallbacks}/{len(cases)} ({fallback_rate:.1%})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
