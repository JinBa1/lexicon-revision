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
import logging
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import chromadb  # noqa: E402
from src.chunking.models import Chunk  # noqa: E402
from src.chunking.pipeline import run_pipeline  # noqa: E402
from src.search.media_sidecar import (  # noqa: E402
    build_storage_media_map,
    write_storage_media_map,
)
from src.search.providers.config import (  # noqa: E402
    build_embedding_provider,
    load_retrieval_provider_settings,
)
from src.search.service import DEFAULT_CHROMA_DIR  # noqa: E402
from src.storage import ArtifactManifest, load_local_manifests  # noqa: E402

logger = logging.getLogger(__name__)

CHROMA_DISTANCE_METADATA_KEY = "hnsw:space"
EMBEDDING_MODEL_METADATA_KEY = "embedding_model_id"


def _encode_texts(model: Any, texts: list[str]) -> list[list[float]]:
    """Encode texts while tolerating both SentenceTransformer and new providers."""
    if hasattr(model, "embed_documents"):
        # New provider protocol
        result = model.embed_documents(texts)
        return result.vectors

    # Legacy SentenceTransformer or simple fake
    try:
        embeddings = model.encode(texts, show_progress_bar=True)
    except TypeError:
        embeddings = model.encode(texts)

    if hasattr(embeddings, "tolist"):
        return embeddings.tolist()
    return embeddings


def _embedding_model_id(model: Any) -> str:
    return str(getattr(model, "model_id", "unknown-model"))


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
    parser.add_argument(
        "--recreate-collection",
        action="store_true",
        help="Delete and recreate the collection if it exists",
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


def index_collection(
    mineru_output_dir: str,
    collection_name: str,
    chroma_dir: str = DEFAULT_CHROMA_DIR,
    metadata_path: str | None = None,
    university: str = "cam",
    embedding_model: Any | None = None,
    recreate_collection: bool = False,
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

    owns_embedding_model = embedding_model is None
    if embedding_model is not None:
        model = embedding_model
    else:
        settings = load_retrieval_provider_settings()
        model = build_embedding_provider(settings)

    try:
        embeddings = _encode_texts(model, embedding_inputs)

        model_id = _embedding_model_id(model)

        ids = [chunk.id for chunk in chunks]
        metadatas = [build_metadata(chunk) for chunk in chunks]

        chroma_path = Path(chroma_dir)
        chroma_path.mkdir(parents=True, exist_ok=True)

        client = chromadb.PersistentClient(path=chroma_dir)

        if recreate_collection:
            try:
                client.delete_collection(collection_name)
            except chromadb.errors.NotFoundError:
                pass

        try:
            collection = client.get_collection(collection_name)
        except chromadb.errors.NotFoundError:
            collection = client.create_collection(
                collection_name,
                metadata={
                    CHROMA_DISTANCE_METADATA_KEY: "cosine",
                    EMBEDDING_MODEL_METADATA_KEY: model_id,
                },
            )
        else:
            _ensure_collection_embedding_model(
                collection=collection,
                collection_name=collection_name,
                model_id=model_id,
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
        manifests = {
            source_pdf: ArtifactManifest.from_json(path.read_text(encoding="utf-8"))
            for source_pdf, path in load_local_manifests(
                Path(mineru_output_dir)
            ).items()
        }
        media_map = build_storage_media_map(chunks=chunks, manifests=manifests)
        try:
            write_storage_media_map(
                output_path=sidecar_path,
                media_map=media_map,
            )
        except OSError:
            logger.exception(
                "Failed to write media sidecar to %s. ChromaDB upserts succeeded; "
                "re-run with the same arguments to retry sidecar creation.",
                sidecar_path,
            )
            raise
    finally:
        if owns_embedding_model:
            _close_if_supported(model)


def _ensure_collection_embedding_model(
    *,
    collection: Any,
    collection_name: str,
    model_id: str,
) -> None:
    metadata = collection.metadata or {}
    existing_model_id = metadata.get(EMBEDDING_MODEL_METADATA_KEY)
    if existing_model_id is None:
        updated_metadata = dict(metadata)
        updated_metadata[EMBEDDING_MODEL_METADATA_KEY] = model_id
        # Chroma rejects updates that include hnsw:space, even unchanged.
        updated_metadata.pop(CHROMA_DISTANCE_METADATA_KEY, None)
        collection.modify(metadata=updated_metadata)
        return

    if existing_model_id != model_id:
        raise ValueError(
            f"Collection '{collection_name}' has {EMBEDDING_MODEL_METADATA_KEY} "
            f"{existing_model_id!r}, but this index run uses {model_id!r}. "
            "Pass --recreate-collection to overwrite it."
        )


def _close_if_supported(provider: Any) -> None:
    close = getattr(provider, "close", None)
    if callable(close):
        close()


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
            recreate_collection=args.recreate_collection,
        )
    except OSError:
        sys.exit(1)


if __name__ == "__main__":
    main()
