"""Run human-authored YAML search evals against the local search backend."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# Allow direct execution via `python scripts/evaluate_search.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.inspect_search import (  # noqa: E402
    build_provider_metadata,
    create_real_search_service,
)
from scripts.search_tooling import (  # noqa: E402
    EvalCase,
    dump_filters,
    load_eval_spec,
    truncate_text,
)
from src.search.errors import (  # noqa: E402
    DEFAULT_MEDIA_DIR,
    CollectionNotFoundError,
    InvalidMetadataFilterError,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the search eval utility."""
    parser = argparse.ArgumentParser(
        description="Run YAML-authored search evaluations",
    )
    parser.add_argument("eval_path", type=Path, help="Path to the YAML eval file")
    parser.add_argument(
        "--media-dir",
        default=DEFAULT_MEDIA_DIR,
        help=f"Media sidecar directory (default: {DEFAULT_MEDIA_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=None,
        help="Override the collection from the eval file",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=None,
        help=(
            "Base maximum number of search results to fetch per case "
            "(default: eval file default_top_k, or 10 if not set)"
        ),
    )
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
        help="Disable cross-encoder reranking",
    )
    parser.set_defaults(rerank=False)
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write the JSON report to this path",
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


def evaluate_cases(
    service: Any,
    cases: list[EvalCase],
    collection: str,
    limit: int,
    rerank: bool,
    name: str = "search_eval",
) -> dict[str, Any]:
    """Run search eval cases and return a stable report structure."""
    if limit <= 0:
        raise ValueError("limit must be positive")

    effective_limit = max(
        limit,
        10,
        max((case.top_k for case in cases), default=10),
    )
    case_reports = [
        _evaluate_case(service, case, collection, effective_limit, rerank)
        for case in cases
    ]
    passed_count = sum(1 for case in case_reports if case["passed"])
    metrics = {
        "hit_at_1": sum(
            1
            for case in case_reports
            if case["matched_rank"] is not None and case["matched_rank"] <= 1
        ),
        "hit_at_3": sum(
            1
            for case in case_reports
            if case["matched_rank"] is not None and case["matched_rank"] <= 3
        ),
        "hit_at_5": sum(
            1
            for case in case_reports
            if case["matched_rank"] is not None and case["matched_rank"] <= 5
        ),
        "hit_at_10": sum(
            1
            for case in case_reports
            if case["matched_rank"] is not None and case["matched_rank"] <= 10
        ),
    }

    return {
        "name": name,
        "collection": collection,
        "limit": limit,
        "effective_limit": effective_limit,
        "providers": build_provider_metadata(service),
        "rerank": rerank,
        "case_count": len(case_reports),
        "passed_count": passed_count,
        "failed_count": len(case_reports) - passed_count,
        "metrics": metrics,
        "cases": case_reports,
    }


def _evaluate_case(
    service: Any,
    case: EvalCase,
    collection: str,
    limit: int,
    rerank: bool,
) -> dict[str, Any]:
    response = service.search(
        query=case.query,
        collection=collection,
        filters=case.filters,
        limit=limit,
        rerank=rerank,
    )

    matched_rank = _find_matched_rank(response.results, case)
    returned = [
        {
            "rank": rank,
            "chunk_id": result.chunk_id,
            "topic": result.metadata.get("topic"),
            "score": result.score,
            "preview": truncate_text(result.text, 120),
        }
        for rank, result in enumerate(response.results[: case.top_k], start=1)
    ]

    passed = matched_rank is not None and matched_rank <= case.top_k
    return {
        "id": case.id,
        "query": case.query,
        "filters": dump_filters(case.filters),
        "expected": {
            "any_chunk_ids": case.any_chunk_ids,
            "any_topics": case.any_topics,
            "top_k": case.top_k,
        },
        "passed": passed,
        "matched_rank": matched_rank,
        "returned": returned,
        "notes": case.notes,
    }


def _find_matched_rank(results: list[Any], case: EvalCase) -> int | None:
    expected_chunk_ids = set(case.any_chunk_ids)
    expected_topics = set(case.any_topics)

    for rank, result in enumerate(results, start=1):
        if result.chunk_id in expected_chunk_ids:
            return rank
        topic = result.metadata.get("topic")
        if isinstance(topic, str) and topic in expected_topics:
            return rank
    return None


def render_json(report: dict[str, Any]) -> str:
    """Render a search evaluation report as stable JSON."""
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)


def render_text(report: dict[str, Any]) -> str:
    """Render a search evaluation report as readable text."""
    lines = [
        f"Search eval: {report['name']}",
        f"Collection: {report['collection']}",
        f"Limit: {report['limit']} (effective: {report['effective_limit']})",
        f"Rerank: {report['rerank']}",
        f"Cases: {report['case_count']}",
        f"Passed: {report['passed_count']}/{report['case_count']}",
        f"Hit@1: {report['metrics']['hit_at_1']}/{report['case_count']}",
        f"Hit@3: {report['metrics']['hit_at_3']}/{report['case_count']}",
        f"Hit@5: {report['metrics']['hit_at_5']}/{report['case_count']}",
        f"Hit@10: {report['metrics']['hit_at_10']}/{report['case_count']}",
        "",
        "Cases:",
    ]

    for case in report["cases"]:
        status = "PASS" if case["passed"] else "FAIL"
        matched_rank = (
            case["matched_rank"] if case["matched_rank"] is not None else "none"
        )
        top_k = case["expected"]["top_k"]
        lines.extend(
            [
                f"- {case['id']} [{status}] matched_rank={matched_rank} top_k={top_k}",
                f"  query: {case['query']}",
                f"  filters: {_format_filters(case['filters'])}",
                f"  expected: {_format_expected(case['expected'])}",
            ]
        )
        if case["notes"]:
            lines.append(f"  notes: {case['notes']}")
        if case["returned"]:
            lines.append("  returned:")
            for result in case["returned"]:
                lines.append(
                    "    "
                    f"{result['rank']}. {result['chunk_id']} "
                    f"topic={_format_scalar(result['topic'])} "
                    f"score={result['score']:.4f}"
                )
        else:
            lines.append("  returned: none")

    failures = [case for case in report["cases"] if not case["passed"]]
    if failures:
        lines.extend(["", "Failures:"])
        for case in failures:
            lines.append(f"- {case['id']}: {_failure_reason(case)}")

    return "\n".join(lines)


def _format_filters(filters: list[dict[str, Any]]) -> str:
    if not filters:
        return "none"
    return "; ".join(
        f"{item['field']} {item['op']} {_format_scalar(item['value'])}"
        for item in filters
    )


def _format_expected(expected: dict[str, Any]) -> str:
    return (
        f"chunk_ids={_format_list(expected['any_chunk_ids'])} "
        f"topics={_format_list(expected['any_topics'])} "
        f"top_k={expected['top_k']}"
    )


def _format_list(values: list[Any]) -> str:
    if not values:
        return "[]"
    return "[" + ", ".join(_format_scalar(value) for value in values) + "]"


def _format_scalar(value: Any) -> str:
    if value is None:
        return "none"
    return str(value)


def _failure_reason(case: dict[str, Any]) -> str:
    if case["matched_rank"] is None:
        return "No expected chunk ID or topic appeared within top_k results."
    return (
        f"Expected match appeared at rank {case['matched_rank']} "
        f"beyond top_k={case['expected']['top_k']}."
    )


def main() -> None:
    """Run the search evaluation CLI."""
    args = parse_args()

    try:
        spec = load_eval_spec(args.eval_path)
        collection = args.collection or spec.collection
        if not collection:
            raise ValueError(
                "Eval file does not declare a collection; pass --collection to override"
            )

        limit = args.limit if args.limit is not None else spec.default_top_k
        service = create_real_search_service(args.media_dir, args.rerank)
        report = evaluate_cases(
            service=service,
            cases=spec.cases,
            collection=collection,
            limit=limit,
            rerank=args.rerank,
            name=spec.name,
        )
        report["description"] = spec.description
        report["eval_path"] = str(args.eval_path)
    except CollectionNotFoundError as exc:
        print(
            f"Collection '{exc.collection_name}' not found.",
            file=sys.stderr,
        )
        print(
            "Index the collection with scripts/index_chunks_postgres.py and try again.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except InvalidMetadataFilterError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    json_output = render_json(report)
    output = json_output if args.format == "json" else render_text(report)
    print(output)
    if args.output is not None:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json_output, encoding="utf-8")
        except OSError as exc:
            print(
                f"Error writing report to {args.output}: {exc}",
                file=sys.stderr,
            )
            raise SystemExit(1) from exc
    if report["failed_count"] > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
