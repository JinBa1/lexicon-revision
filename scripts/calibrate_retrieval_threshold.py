"""Calibrate retrieval abstention thresholds with positive and negative queries."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow direct execution via `python scripts/calibrate_retrieval_threshold.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate_search import evaluate_cases  # noqa: E402
from scripts.inspect_search import build_provider_metadata  # noqa: E402
from scripts.search_tooling import (  # noqa: E402
    EvalCase,
    dump_filters,
    load_eval_spec,
    truncate_text,
)
from src.db.config import load_database_settings  # noqa: E402
from src.search.base import SearchBackend  # noqa: E402
from src.search.factory import create_search_service  # noqa: E402
from src.search.providers.config import (  # noqa: E402
    RetrievalProviderSettings,
    build_embedding_provider,
    build_rerank_provider,
    load_retrieval_provider_settings,
)

DEFAULT_NEGATIVE_QUERIES = [
    "renaissance oil painting glazing techniques",
    "Italian personal income tax filing deadline",
    "heart valve replacement recovery timeline",
    "Shakespeare sonnet meter analysis",
    "NBA playoff bracket seeding rules",
    "sourdough starter hydration troubleshooting",
    "quantum chromodynamics Feynman diagrams",
    "CRISPR Cas9 off target gene editing",
    "lithium ion battery cathode degradation",
    "finite element mesh refinement for bridges",
    "Kubernetes ingress controller TLS termination",
    "Rust borrow checker lifetime elision",
    "compiler register allocation graph coloring",
    "distributed consensus Byzantine fault tolerance",
    "GPU shader texture sampling anisotropy",
    "cryptocurrency proof of stake slashing",
    "large language model RLHF reward hacking",
    "homomorphic encryption bootstrapping circuits",
    "florbnicate zargle tensor marmalade",
    "ZXQ-17 blue banana protocol",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Calibrate retrieval abstention thresholds",
    )
    parser.add_argument(
        "eval_path",
        type=Path,
        help="Positive search eval YAML, e.g. evals/cambridge_fixture_v1.yaml",
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
        help="Base positive/negative retrieval limit; effective minimum is 10",
    )
    rerank_group = parser.add_mutually_exclusive_group()
    rerank_group.add_argument(
        "--rerank",
        dest="rerank",
        action="store_true",
        help="Apply the configured reranker",
    )
    rerank_group.add_argument(
        "--no-rerank",
        dest="rerank",
        action="store_false",
        help="Disable reranking",
    )
    parser.set_defaults(rerank=True)
    parser.add_argument(
        "--negative-query",
        dest="negative_queries",
        action="append",
        default=[],
        help="Additional negative query; repeatable",
    )
    parser.add_argument(
        "--negative-query-file",
        type=Path,
        help="Optional newline-delimited negative query file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory for calibration_raw.json and summary.md "
            "(default: local/reports/retrieval-calibration/<timestamp>)"
        ),
    )
    parser.add_argument(
        "--expect-embedding-model-id",
        default=None,
        help="Fail unless the created search service reports this embedding model ID",
    )
    parser.add_argument(
        "--expect-rerank-model-id",
        default=None,
        help="Fail unless the created search service reports this rerank model ID",
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


def create_real_search_service(
    *,
    rerank: bool,
) -> SearchBackend:
    """Create a real service for raw calibration with thresholds disabled."""
    provider_settings = load_retrieval_provider_settings()
    provider_settings = RetrievalProviderSettings(
        embedding=provider_settings.embedding,
        rerank=provider_settings.rerank,
        rerank_enabled=rerank,
        voyage_api_key=provider_settings.voyage_api_key,
    )
    embedding_model = build_embedding_provider(provider_settings)
    reranker = build_rerank_provider(provider_settings)
    return create_search_service(
        database_settings=load_database_settings(),
        embedding_model=embedding_model,
        reranker=reranker,
        apply_collection_thresholds=False,
    )


create_calibration_search_service = create_real_search_service


def run_calibration(
    *,
    service: SearchBackend,
    eval_name: str,
    positive_cases: list[EvalCase],
    collection: str,
    limit: int,
    rerank: bool,
    negative_queries: list[str],
) -> dict[str, Any]:
    positive_report = evaluate_cases(
        service=service,
        cases=positive_cases,
        collection=collection,
        limit=limit,
        rerank=rerank,
        name=eval_name,
    )
    effective_limit = int(positive_report["effective_limit"])
    negative_cases = [
        _evaluate_negative_query(
            service=service,
            query=query,
            collection=collection,
            limit=effective_limit,
            rerank=rerank,
        )
        for query in negative_queries
    ]
    negative_report = {
        "case_count": len(negative_cases),
        "cases": negative_cases,
    }
    return {
        "name": f"{eval_name}_threshold_calibration",
        "collection": collection,
        "limit": limit,
        "effective_limit": effective_limit,
        "rerank": rerank,
        "providers": build_provider_metadata(service),
        "positive": positive_report,
        "negative": negative_report,
        "analysis": analyze_score_gap(positive_report, negative_report),
    }


def assert_expected_models(
    *,
    service: SearchBackend,
    expected_embedding_model_id: str | None,
    expected_rerank_model_id: str | None,
) -> None:
    embedding_model_id = getattr(service, "embedding_model_id", None)
    rerank_model_id = getattr(service, "rerank_model_id", None)
    if (
        expected_embedding_model_id is not None
        and embedding_model_id != expected_embedding_model_id
    ):
        raise SystemExit(
            "Expected embedding model "
            f"{expected_embedding_model_id!r}, got {embedding_model_id!r}"
        )
    if (
        expected_rerank_model_id is not None
        and rerank_model_id != expected_rerank_model_id
    ):
        raise SystemExit(
            f"Expected rerank model {expected_rerank_model_id!r}, "
            f"got {rerank_model_id!r}"
        )


def _evaluate_negative_query(
    *,
    service: SearchBackend,
    query: str,
    collection: str,
    limit: int,
    rerank: bool,
) -> dict[str, Any]:
    response = service.search(
        query=query,
        collection=collection,
        filters=None,
        limit=limit,
        rerank=rerank,
    )
    returned = [
        {
            "rank": rank,
            "chunk_id": result.chunk_id,
            "topic": result.metadata.get("topic"),
            "score": result.score,
            "preview": truncate_text(result.text, 120),
        }
        for rank, result in enumerate(response.results, start=1)
    ]
    return {
        "query": query,
        "filters": dump_filters([]),
        "top_score": returned[0]["score"] if returned else None,
        "returned": returned,
    }


def analyze_score_gap(
    positive_report: dict[str, Any],
    negative_report: dict[str, Any],
) -> dict[str, Any]:
    positive_scores = _matched_positive_scores(positive_report)
    negative_scores = [
        case["top_score"]
        for case in negative_report["cases"]
        if case["top_score"] is not None
    ]
    weakest_positive = min(positive_scores, default=None)
    strongest_negative = max(negative_scores, default=None)
    has_clean_gap = (
        weakest_positive is not None
        and strongest_negative is not None
        and strongest_negative < weakest_positive
    )
    suggested = None
    if has_clean_gap:
        suggested = round(
            strongest_negative + ((weakest_positive - strongest_negative) / 2),
            4,
        )
    return {
        "weakest_positive_score": weakest_positive,
        "strongest_negative_score": strongest_negative,
        "suggested_rerank_min_score": suggested,
        "has_clean_gap": has_clean_gap,
        "matched_positive_scores": positive_scores,
        "negative_top_scores": negative_scores,
    }


def _matched_positive_scores(positive_report: dict[str, Any]) -> list[float]:
    scores: list[float] = []
    for case in positive_report["cases"]:
        matched_rank = case["matched_rank"]
        if matched_rank is None:
            continue
        for result in case["returned"]:
            if result["rank"] == matched_rank:
                scores.append(result["score"])
                break
    return scores


def write_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_json_path = output_dir / "calibration_raw.json"
    summary_path = output_dir / "summary.md"
    raw_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    summary_path.write_text(render_markdown(report), encoding="utf-8")
    return {
        "raw_json": raw_json_path,
        "summary": summary_path,
    }


def render_markdown(report: dict[str, Any]) -> str:
    analysis = report["analysis"]
    lines = [
        "# Retrieval Threshold Calibration Summary",
        "",
        f"- Name: `{report['name']}`",
        f"- Collection: `{report['collection']}`",
        f"- Rerank: `{report['rerank']}`",
        f"- Embedding model: `{report['providers']['embedding_model_id']}`",
        f"- Rerank model: `{report['providers']['rerank_model_id']}`",
        (
            f"- Positive eval passed: "
            f"{report['positive']['passed_count']}/{report['positive']['case_count']}"
        ),
        f"- Negative queries: {report['negative']['case_count']}",
        "",
        "## Score Gap",
        "",
        "- Weakest matched positive score: "
        f"`{_format_score(analysis['weakest_positive_score'])}`",
        "- Strongest negative top score: "
        f"`{_format_score(analysis['strongest_negative_score'])}`",
    ]
    if analysis["has_clean_gap"]:
        lines.append(
            "- Suggested collection `retrieval_rerank_min_score`: "
            f"`{analysis['suggested_rerank_min_score']}`"
        )
        lines.append(
            "- Apply it to the calibrated collection row before relying on "
            "abstention behavior."
        )
    else:
        lines.append("- No clean positive/negative score gap was found.")

    lines.extend(["", "## Positive Cases", ""])
    for case in report["positive"]["cases"]:
        lines.append(
            f"- `{case['id']}` passed={case['passed']} "
            f"matched_rank={case['matched_rank']} "
            f"matched_score={_format_score(_case_matched_score(case))}"
        )

    lines.extend(["", "## Negative Queries", ""])
    for case in report["negative"]["cases"]:
        lines.append(
            f"- `{case['query']}` top_score={_format_score(case['top_score'])}"
        )

    return "\n".join(lines) + "\n"


def _case_matched_score(case: dict[str, Any]) -> float | None:
    matched_rank = case["matched_rank"]
    if matched_rank is None:
        return None
    for result in case["returned"]:
        if result["rank"] == matched_rank:
            return result["score"]
    return None


def _format_score(score: float | None) -> str:
    if score is None:
        return "none"
    return f"{score:.6g}"


def _load_negative_queries(args: argparse.Namespace) -> list[str]:
    queries = list(DEFAULT_NEGATIVE_QUERIES)
    if args.negative_query_file is not None:
        raw_lines = args.negative_query_file.read_text(encoding="utf-8").splitlines()
        queries.extend(line.strip() for line in raw_lines if line.strip())
    queries.extend(args.negative_queries)
    return list(dict.fromkeys(queries))


def _default_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("local/reports/retrieval-calibration") / timestamp


def main() -> None:
    args = parse_args()
    spec = load_eval_spec(args.eval_path)
    collection = args.collection or spec.collection
    if collection is None:
        raise SystemExit("Eval file does not declare a collection; pass --collection")
    limit = args.limit or spec.default_top_k
    service = create_real_search_service(rerank=args.rerank)
    assert_expected_models(
        service=service,
        expected_embedding_model_id=args.expect_embedding_model_id,
        expected_rerank_model_id=args.expect_rerank_model_id,
    )
    report = run_calibration(
        service=service,
        eval_name=spec.name,
        positive_cases=spec.cases,
        collection=collection,
        limit=limit,
        rerank=args.rerank,
        negative_queries=_load_negative_queries(args),
    )
    output_dir = args.output_dir or _default_output_dir()
    paths = write_outputs(report, output_dir)
    print(f"Wrote raw JSON: {paths['raw_json']}")
    print(f"Wrote summary: {paths['summary']}")


if __name__ == "__main__":
    main()
