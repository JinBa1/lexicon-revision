"""Inspect local ChromaDB collection contents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Allow direct execution via `python scripts/inspect_chroma.py ...`.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chromadb  # noqa: E402
from chromadb.errors import NotFoundError  # noqa: E402
from scripts.search_tooling import load_media_map, truncate_text  # noqa: E402
from src.search.service import DEFAULT_CHROMA_DIR, DEFAULT_COLLECTION  # noqa: E402


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the Chroma inspection utility."""
    parser = argparse.ArgumentParser(
        description="Inspect local ChromaDB contents",
    )
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
        "--list-collections",
        action="store_true",
        help="List collection names and exit",
    )
    parser.add_argument(
        "--peek",
        type=_positive_int,
        default=5,
        help="Number of sample records to inspect when no chunk ID is provided",
    )
    parser.add_argument(
        "--chunk-id",
        help="Exact chunk ID to inspect",
    )
    parser.add_argument(
        "--limit",
        type=_positive_int,
        default=20,
        help="Maximum number of records to inspect",
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
        help="Preview length for document text",
    )
    parser.add_argument(
        "--show-media",
        action="store_true",
        help="Include media sidecar entries in the report",
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


class CollectionNotFoundError(RuntimeError):
    """Raised when the requested Chroma collection does not exist."""

    def __init__(self, collection_name: str) -> None:
        super().__init__(collection_name)
        self.collection_name = collection_name


def list_collection_names(chroma_dir: str) -> list[str]:
    """Return sorted collection names from a Chroma persistent directory."""
    client = chromadb.PersistentClient(path=chroma_dir)
    return sorted(collection.name for collection in client.list_collections())


def build_collection_report(
    *,
    chroma_dir: str,
    collection_name: str,
    peek: int,
    chunk_id: str | None,
    limit: int,
    show_media: bool,
    max_text_chars: int,
) -> dict[str, Any]:
    """Build a stable report of stored Chroma records and sidecar metadata."""
    client = chromadb.PersistentClient(path=chroma_dir)
    try:
        collection = client.get_collection(collection_name)
    except NotFoundError as exc:
        raise CollectionNotFoundError(collection_name) from exc
    media_map = load_media_map(chroma_dir, collection_name)
    sidecar_path = Path(chroma_dir) / f"{collection_name}_media_map.json"

    records = _load_records(
        collection=collection,
        media_map=media_map,
        chunk_id=chunk_id,
        peek=peek,
        limit=limit,
        max_text_chars=max_text_chars,
        show_media=show_media,
    )

    return {
        "collection": collection_name,
        "chroma_dir": chroma_dir,
        "count": collection.count(),
        "sidecar_path": str(sidecar_path),
        "media_entry_count": len(media_map),
        "records": records,
    }


def _load_records(
    *,
    collection: Any,
    media_map: dict[str, list[dict[str, Any]]],
    chunk_id: str | None,
    peek: int,
    limit: int,
    max_text_chars: int,
    show_media: bool,
) -> list[dict[str, Any]]:
    if chunk_id is not None:
        raw = collection.get(ids=[chunk_id], include=["documents", "metadatas"])
    else:
        sample_size = limit if peek <= 0 else min(peek, limit)
        raw = collection.get(
            limit=sample_size,
            include=["documents", "metadatas"],
        )

    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []

    records: list[dict[str, Any]] = []
    for item_id, document, metadata in zip(ids, documents, metadatas, strict=True):
        metadata_dict = metadata or {}
        media_refs = media_map.get(item_id, [])
        record: dict[str, Any] = {
            "id": item_id,
            "metadata": metadata_dict,
            "document_preview": truncate_text(document or "", max_text_chars),
            "media_count": len(media_refs),
        }
        if show_media:
            record["media"] = media_refs
        records.append(record)

    return records


def render_json(report: dict[str, Any]) -> str:
    """Render a collection report as stable JSON."""
    return json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True)


def render_text(report: dict[str, Any]) -> str:
    """Render a collection report as readable text."""
    lines = [
        f"Collection: {report['collection']}",
        f"Chroma dir: {report['chroma_dir']}",
        f"Count: {report['count']}",
        f"Media sidecar: {report['sidecar_path']}",
        f"Media entries: {report['media_entry_count']}",
    ]

    records = report["records"]
    if not records:
        lines.append("")
        lines.append("No records matched the requested lookup.")
        return "\n".join(lines)

    for record in records:
        metadata = record["metadata"]
        lines.extend(
            [
                "",
                f"Record: {record['id']}",
                (
                    "metadata: "
                    f"year={_format_text_value(metadata.get('year'))} "
                    f"paper={_format_text_value(metadata.get('paper'))} "
                    f"question={_format_text_value(metadata.get('question_number'))} "
                    f"topic={_format_text_value(metadata.get('topic'))} "
                    f"level={_format_text_value(metadata.get('chunk_level'))} "
                    f"source={_format_text_value(metadata.get('source_pdf'))}"
                ),
                f"media={record['media_count']}",
                "preview:",
                record["document_preview"],
            ]
        )
        for media_ref in record.get("media", []):
            lines.append(
                (
                    "  - "
                    f"media_id={media_ref.get('media_id')} "
                    f"kind={media_ref.get('kind')} "
                    f"relation={media_ref.get('relation')} "
                    f"object_key={media_ref.get('object_key')}"
                )
            )

    return "\n".join(lines)


def _format_text_value(value: Any) -> str:
    if value is None:
        return "None"
    return str(value)


def main() -> None:
    """Run the Chroma inspection CLI."""
    args = parse_args()

    if args.list_collections:
        for collection_name in list_collection_names(args.chroma_dir):
            print(collection_name)
        return

    try:
        report = build_collection_report(
            chroma_dir=args.chroma_dir,
            collection_name=args.collection,
            peek=args.peek,
            chunk_id=args.chunk_id,
            limit=args.limit,
            show_media=args.show_media,
            max_text_chars=args.max_text_chars,
        )
    except CollectionNotFoundError:
        print(
            (
                f"Collection {args.collection!r} not found. "
                "Use --list-collections to inspect available collections."
            ),
            file=sys.stderr,
        )
        raise SystemExit(1)
    output = render_json(report) if args.format == "json" else render_text(report)
    print(output)


if __name__ == "__main__":
    main()
