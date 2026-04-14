"""Offline indexing: chunk -> embed -> ChromaDB + media sidecar.

Usage:
    python scripts/index_chunks.py \
        --input data/mineru_output/ \
        --collection cam-cs-tripos \
        --metadata data/papers/metadata.json \
        --chroma-dir ./chroma_data
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chromadb  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402
from src.chunking.models import Chunk  # noqa: E402
from src.chunking.pipeline import run_pipeline  # noqa: E402
from src.search.service import DEFAULT_CHROMA_DIR, EMBEDDING_MODEL_NAME  # noqa: E402

logger = logging.getLogger(__name__)


def _encode_texts(model: object, texts: list[str]) -> Any:
    """Encode texts while tolerating simpler fake embedders in tests."""
    try:
        return model.encode(texts, show_progress_bar=True)
    except TypeError:
        return model.encode(texts)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the offline indexer."""
    parser = argparse.ArgumentParser(
        description="Index chunked exam questions into ChromaDB",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Directory containing MinerU output",
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="ChromaDB collection name (for example: cam-cs-tripos)",
    )
    parser.add_argument(
        "--metadata",
        default=None,
        help="Path to downloader metadata.json",
    )
    parser.add_argument(
        "--chroma-dir",
        default=DEFAULT_CHROMA_DIR,
        help=f"ChromaDB storage directory (default: {DEFAULT_CHROMA_DIR})",
    )
    parser.add_argument(
        "--university",
        default="cam",
        help="University code used in chunk IDs (default: cam)",
    )
    return parser.parse_args()


def build_embedding_text(chunk: Chunk) -> str:
    """Build the embedding input from raw text plus a short metadata footer."""
    parts = [chunk.text.strip()]
    footer_fields: list[str] = []

    if chunk.year is not None:
        footer_fields.append(f"Year: {chunk.year}")
    if chunk.paper is not None:
        footer_fields.append(f"Paper: {chunk.paper}")
    if chunk.question_number is not None:
        footer_fields.append(f"Question: {chunk.question_number}")
    if chunk.topic is not None:
        footer_fields.append(f"Topic: {chunk.topic}")

    if footer_fields:
        parts.append(" | ".join(footer_fields))

    return "\n\n".join(parts)


def build_metadata(chunk: Chunk) -> dict[str, Any]:
    """Extract scalar metadata for ChromaDB storage."""
    return {
        "year": chunk.year,
        "paper": chunk.paper,
        "question_number": chunk.question_number,
        "topic": chunk.topic,
        "author": chunk.author,
        "tripos_part": chunk.tripos_part,
        "chunk_level": chunk.chunk_level,
        "parent_chunk_id": chunk.parent_chunk_id,
        "sub_question_label": chunk.sub_question_label,
        "marks": chunk.marks,
        "total_marks": chunk.total_marks,
        "has_code": chunk.has_code,
        "has_figure": chunk.has_figure,
        "has_table": chunk.has_table,
        "source_pdf": chunk.source_pdf,
    }


def build_media_map(chunks: list[Chunk]) -> dict[str, list[dict[str, Any]]]:
    """Build the chunk_id -> media sidecar mapping."""
    media_map: dict[str, list[dict[str, Any]]] = {}
    for chunk in chunks:
        if not chunk.media:
            continue
        media_map[chunk.id] = [
            {
                "media_id": ref.media_id,
                "kind": ref.kind,
                "file_path": ref.file_path,
                "relation": ref.relation,
                "page_number": ref.page_number,
                "bbox": list(ref.bbox) if ref.bbox is not None else None,
                "owner_level": ref.owner_level,
                "owner_label": ref.owner_label,
                "order_index": ref.order_index,
                "text_payload": ref.text_payload,
                "description": ref.description,
            }
            for ref in chunk.media
        ]
    return media_map


def index_collection(
    mineru_output_dir: str,
    collection_name: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    metadata_path: str | None = None,
    university: str = "cam",
    embedding_model: object | None = None,
) -> None:
    """Index chunk output into ChromaDB and write the media sidecar.

    This is an upsert-only rebuild step keyed by chunk ID. It intentionally
    does not delete stale collection entries that are absent from the current
    corpus snapshot.
    """
    chunks = run_pipeline(
        mineru_output_dir=mineru_output_dir,
        metadata_path=metadata_path,
        university=university,
    )
    if not chunks:
        logger.warning(
            "No chunks produced from %s; nothing to index",
            mineru_output_dir,
        )
        return

    documents = [chunk.text.strip() for chunk in chunks]
    embedding_inputs = [build_embedding_text(chunk) for chunk in chunks]

    model = (
        embedding_model
        if embedding_model is not None
        else SentenceTransformer(EMBEDDING_MODEL_NAME)
    )
    embeddings = _encode_texts(model, embedding_inputs)
    if hasattr(embeddings, "tolist"):
        embeddings = embeddings.tolist()

    ids = [chunk.id for chunk in chunks]
    metadatas = [build_metadata(chunk) for chunk in chunks]

    chroma_path = Path(chroma_dir)
    chroma_path.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_dir)
    collection = client.get_or_create_collection(
        collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 500
    for start in range(0, len(ids), batch_size):
        end = start + batch_size
        collection.upsert(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=embeddings[start:end],
            metadatas=metadatas[start:end],
        )

    sidecar_path = chroma_path / f"{collection_name}_media_map.json"
    media_map = build_media_map(chunks)
    sidecar_json = json.dumps(media_map, indent=2, ensure_ascii=False)

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=chroma_path,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as handle:
            handle.write(sidecar_json)
            tmp_path = Path(handle.name)
        tmp_path.replace(sidecar_path)
    except OSError:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        logger.exception(
            "Failed to write media sidecar to %s. ChromaDB upserts succeeded; "
            "re-run with the same arguments to retry sidecar creation.",
            sidecar_path,
        )
        raise


def main() -> None:
    """Run the indexing CLI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()
    try:
        index_collection(
            mineru_output_dir=args.input,
            collection_name=args.collection,
            chroma_dir=args.chroma_dir,
            metadata_path=args.metadata,
            university=args.university,
        )
    except OSError:
        sys.exit(1)


if __name__ == "__main__":
    main()
