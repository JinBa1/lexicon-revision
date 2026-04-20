"""Inspect local search results without running FastAPI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow direct execution via `python scripts/inspect_search.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.search_tooling import (  # noqa: E402
    build_filters,
    dump_filters,
    parse_filter_conditions,
    truncate_text,
)
from src.db.config import load_database_settings  # noqa: E402
from src.metadata_schema.models import FilterCondition  # noqa: E402
from src.search.base import SearchBackend  # noqa: E402
from src.search.errors import (  # noqa: E402
    DEFAULT_COLLECTION,
    DEFAULT_MEDIA_DIR,
    CollectionNotFoundError,
    InvalidMetadataFilterError,
)
from src.search.factory import create_search_service  # noqa: E402
from src.search.models import SearchResponse  # noqa: E402
from src.search.providers.config import (  # noqa: E402
    RetrievalProviderSettings,
    build_embedding_provider,
    build_rerank_provider,
    load_retrieval_provider_settings,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the search inspection utility."""
    parser = argparse.ArgumentParser(
        description="Inspect local search results",
    )
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "--media-dir",
        default=DEFAULT_MEDIA_DIR,
        help=f"Media sidecar directory (default: {DEFAULT_MEDIA_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"Search collection name (default: {DEFAULT_COLLECTION})",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help="Maximum number of results to return",
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
    parser.set_defaults(rerank=True)
    parser.add_argument("--year", type=int, help="Filter by year")
    parser.add_argument("--paper", type=int, help="Filter by paper number")
    parser.add_argument("--topic", help="Filter by topic")
    parser.add_argument("--question", type=int, help="Filter by question number")
    parser.add_argument(
        "--marks-min",
        type=int,
        help="Minimum marks filter",
    )
    parser.add_argument(
        "--has-code",
        action="store_true",
        help="Filter for chunks with code",
    )
    parser.add_argument(
        "--has-figure",
        action="store_true",
        help="Filter for chunks with figures",
    )
    parser.add_argument(
        "--has-table",
        action="store_true",
        help="Filter for chunks with tables",
    )
    parser.add_argument(
        "--filter",
        dest="filters",
        action="append",
        default=[],
        help="Repeatable filter in field:op:value form, e.g. year:eq:2024",
    )
    parser.add_argument(
        "--show-media",
        action="store_true",
        help="Include media refs in the report",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format",
    )
    parser.add_argument(
        "--max-text-chars",
        type=_positive_int,
        default=500,
        help="Preview length for result text",
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
    media_dir: str,
    rerank: bool,
    reranker_device: str | None = None,
) -> SearchBackend:
    """Create a search backend backed by configured retrieval providers.

    `reranker_device` accepts "cpu", "cuda", or "auto"/None (let CrossEncoder
    pick). It only affects the local reranker provider.
    """
    provider_settings = load_retrieval_provider_settings()
    provider_settings = RetrievalProviderSettings(
        embedding=provider_settings.embedding,
        rerank=provider_settings.rerank,
        rerank_enabled=rerank,
        voyage_api_key=provider_settings.voyage_api_key,
    )
    embedding_model = build_embedding_provider(provider_settings)
    device = None if reranker_device in (None, "auto") else reranker_device
    reranker = build_rerank_provider(provider_settings, device=device)
    db_settings = load_database_settings()
    return create_search_service(
        database_settings=db_settings,
        embedding_model=embedding_model,
        reranker=reranker,
        media_dir=media_dir,
    )


def build_search_payload(
    service: SearchBackend,
    query: str,
    collection: str,
    filters: list[FilterCondition],
    limit: int,
    rerank: bool,
    show_media: bool,
    max_text_chars: int,
) -> dict[str, Any]:
    """Run search and convert the response into CLI-friendly payload data."""
    response: SearchResponse = service.search(
        query=query,
        collection=collection,
        filters=filters or None,
        limit=limit,
        rerank=rerank,
    )

    payload = response.model_dump()
    payload.update(
        {
            "filters": dump_filters(filters),
            "limit": limit,
            "providers": build_provider_metadata(service),
            "rerank": rerank,
            "show_media": show_media,
            "max_text_chars": max_text_chars,
        }
    )
    payload["results"] = [
        {
            **result,
            "text_preview": truncate_text(result["text"], max_text_chars),
        }
        for result in payload["results"]
    ]
    return payload


def build_provider_metadata(service: object) -> dict[str, str | None]:
    return {
        "embedding_model_id": getattr(service, "embedding_model_id", None),
        "rerank_model_id": getattr(service, "rerank_model_id", None),
    }


def render_json(payload: dict[str, Any]) -> str:
    """Render a search payload as stable JSON."""
    return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)


def render_text(payload: dict[str, Any]) -> str:
    """Render a search payload as readable text."""
    filters = payload.get("filters") or {}
    lines = [
        f"Query: {payload['query']}",
        f"Collection: {payload['collection']}",
        f"Filters: {_format_filters(filters)}",
        f"Limit: {payload['limit']}",
        f"Rerank: {payload['rerank']}",
        f"Show media: {payload['show_media']}",
        f"Total: {payload['total']}",
    ]

    results = payload["results"]
    if not results:
        lines.append("")
        lines.append("No results matched the requested search.")
        return "\n".join(lines)

    for index, result in enumerate(results, start=1):
        lines.extend(
            [
                "",
                f"{index}. {result['chunk_id']}",
                f"   score: {result['score']:.4f}",
                f"   metadata: {_format_metadata(result['metadata'])}",
                f"   preview: {result['text_preview']}",
            ]
        )
        if payload["show_media"] and result["media"]:
            lines.append("   media:")
            for media_ref in result["media"]:
                lines.append(
                    (
                        "     - "
                        f"media_id={media_ref.get('media_id')} "
                        f"kind={media_ref.get('kind')} "
                        f"relation={media_ref.get('relation')} "
                        f"object_key={media_ref.get('object_key')} "
                        f"access_url={media_ref.get('access_url')}"
                    )
                )

    return "\n".join(lines)


def _format_filters(filters: list[dict[str, Any]]) -> str:
    if not filters:
        return "none"
    return "; ".join(
        f"{item['field']} {item['op']} {item['value']}" for item in filters
    )


def _format_metadata(metadata: dict[str, Any]) -> str:
    return " ".join(
        f"{key}={metadata[key]}"
        for key in sorted(metadata)
        if metadata.get(key) is not None
    )


def main() -> None:
    """Run the local search inspection CLI."""
    args = parse_args()
    filters = build_filters(
        year=args.year,
        paper=args.paper,
        topic=args.topic,
        question=args.question,
        marks_min=args.marks_min,
        has_code=True if args.has_code else None,
        has_figure=True if args.has_figure else None,
        has_table=True if args.has_table else None,
    )
    filters.extend(parse_filter_conditions(args.filters))

    try:
        service = create_real_search_service(
            args.media_dir,
            args.rerank,
        )
        payload = build_search_payload(
            service=service,
            query=args.query,
            collection=args.collection,
            filters=filters,
            limit=args.limit,
            rerank=args.rerank,
            show_media=args.show_media,
            max_text_chars=args.max_text_chars,
        )
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
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    output = render_json(payload) if args.format == "json" else render_text(payload)
    print(output)


if __name__ == "__main__":
    main()
