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

from scripts.search_tooling import build_filters, truncate_text  # noqa: E402
from src.search.models import SearchResponse  # noqa: E402
from src.search.service import (  # noqa: E402
    DEFAULT_CHROMA_DIR,
    DEFAULT_COLLECTION,
    EMBEDDING_MODEL_NAME,
    METADATA_KEYS,
    RERANKER_MODEL_NAME,
    CollectionNotFoundError,
    SearchService,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the search inspection utility."""
    parser = argparse.ArgumentParser(
        description="Inspect local search results",
    )
    parser.add_argument("query", help="Search query text")
    parser.add_argument(
        "--chroma-dir",
        default=DEFAULT_CHROMA_DIR,
        help=f"ChromaDB storage directory (default: {DEFAULT_CHROMA_DIR})",
    )
    parser.add_argument(
        "--collection",
        default=DEFAULT_COLLECTION,
        help=f"ChromaDB collection name (default: {DEFAULT_COLLECTION})",
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
    chroma_dir: str,
    rerank: bool,
    reranker_device: str | None = None,
) -> SearchService:
    """Create a SearchService backed by real sentence-transformer models.

    `reranker_device` accepts "cpu", "cuda", or "auto"/None (let CrossEncoder
    pick). Used to keep GPU off the reranker when Ollama owns the GPU.
    """
    from sentence_transformers import CrossEncoder, SentenceTransformer

    embedding_model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    if rerank:
        device = None if reranker_device in (None, "auto") else reranker_device
        reranker = (
            CrossEncoder(RERANKER_MODEL_NAME, device=device)
            if device is not None
            else CrossEncoder(RERANKER_MODEL_NAME)
        )
    else:
        reranker = None
    return SearchService(
        chroma_dir=chroma_dir,
        embedding_model=embedding_model,
        reranker=reranker,
    )


def build_search_payload(
    service: SearchService,
    query: str,
    collection: str,
    filters: dict[str, Any],
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
            "filters": filters,
            "limit": limit,
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
                        f"file_path={media_ref.get('file_path')}"
                    )
                )

    return "\n".join(lines)


def _format_filters(filters: dict[str, Any]) -> str:
    if not filters:
        return "none"
    return " ".join(f"{key}={value}" for key, value in filters.items())


def _format_metadata(metadata: dict[str, Any]) -> str:
    return " ".join(f"{key}={metadata.get(key)}" for key in METADATA_KEYS)


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

    try:
        service = create_real_search_service(args.chroma_dir, args.rerank)
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
            "Use scripts/inspect_chroma.py --list-collections to inspect available "
            "collections.",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    output = render_json(payload) if args.format == "json" else render_text(payload)
    print(output)


if __name__ == "__main__":
    main()
