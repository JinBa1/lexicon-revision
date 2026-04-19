"""Offline indexing: chunk -> embed -> PostgreSQL (pgvector).

Usage:
    python scripts/index_chunks_postgres.py \
        --input data/mineru_output/ \
        --collection cam-cs-tripos
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

from scripts.index_chunks import build_embedding_text  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from src.chunking.pipeline import run_pipeline  # noqa: E402
from src.db.config import create_database_engine, load_database_settings  # noqa: E402
from src.db.metadata_indexes import ensure_metadata_indexes  # noqa: E402
from src.metadata_schema import (  # noqa: E402
    default_schema_path,
    load_collection_schema,
)
from src.search.media_sidecar import (  # noqa: E402
    build_storage_media_map,
    write_storage_media_map,
)
from src.search.pg_repository import PgIndexRepository  # noqa: E402
from src.search.providers.config import (  # noqa: E402
    build_embedding_provider,
    load_retrieval_provider_settings,
)
from src.search.service import DEFAULT_CHROMA_DIR  # noqa: E402
from src.storage import ArtifactManifest, load_local_manifests  # noqa: E402

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index chunked exam questions into PostgreSQL (pgvector)",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Directory containing MinerU output",
    )
    parser.add_argument(
        "--collection",
        required=True,
        help="Collection name (for example: cam-cs-tripos)",
    )
    parser.add_argument(
        "--metadata",
        default=None,
        help="Path to downloader metadata.json",
    )
    parser.add_argument(
        "--metadata-schema",
        default=None,
        help="Path to the collection metadata schema JSON file",
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


def index_collection_postgres(
    mineru_output_dir: str,
    collection_name: str,
    engine: Engine,
    embedding_model: Any,
    embedding_dimension: int,
    metadata_path: str | None = None,
    metadata_schema_path: str | None = None,
    university: str = "cam",
    recreate_collection: bool = False,
) -> None:
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

    manifests = {
        source_pdf: ArtifactManifest.from_json(path.read_text(encoding="utf-8"))
        for source_pdf, path in load_local_manifests(Path(mineru_output_dir)).items()
    }
    media_map = build_storage_media_map(chunks=chunks, manifests=manifests)

    embedding_inputs = [build_embedding_text(chunk) for chunk in chunks]
    result = embedding_model.embed_documents(embedding_inputs)
    vectors = result.vectors
    schema_path = metadata_schema_path or default_schema_path(collection_name)
    metadata_schema = load_collection_schema(schema_path)

    repo = PgIndexRepository(
        engine=engine,
        embedding_model_id=embedding_model.model_id,
        embedding_dimension=embedding_dimension,
    )

    if recreate_collection:
        repo.recreate_collection(collection_name)

    repo.index_chunks(
        collection_name=collection_name,
        chunks=chunks,
        vectors=vectors,
        metadata_schema=metadata_schema,
    )
    ensure_metadata_indexes(
        engine,
        collection_name=collection_name,
        schema=metadata_schema,
    )
    _write_media_sidecar(
        collection_name=collection_name,
        media_map=media_map,
        media_dir=DEFAULT_CHROMA_DIR,
    )


def _write_media_sidecar(
    *,
    collection_name: str,
    media_map: dict[str, list[dict[str, Any]]],
    media_dir: str = DEFAULT_CHROMA_DIR,
) -> None:
    media_root = Path(media_dir)
    media_root.mkdir(parents=True, exist_ok=True)
    sidecar_path = media_root / f"{collection_name}_media_map.json"
    try:
        write_storage_media_map(
            output_path=sidecar_path,
            media_map=media_map,
        )
    except OSError:
        logger.exception("Failed to write Postgres media sidecar to %s", sidecar_path)
        raise


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()
    try:
        db_settings = load_database_settings()
        engine = create_database_engine(db_settings)
        provider_settings = load_retrieval_provider_settings()
        embedding_model = build_embedding_provider(provider_settings)
        try:
            index_collection_postgres(
                mineru_output_dir=args.input,
                collection_name=args.collection,
                engine=engine,
                embedding_model=embedding_model,
                embedding_dimension=db_settings.embedding_dimension,
                metadata_path=args.metadata,
                metadata_schema_path=args.metadata_schema,
                university=args.university,
                recreate_collection=args.recreate_collection,
            )
        finally:
            close = getattr(embedding_model, "close", None)
            if callable(close):
                close()
    except OSError:
        sys.exit(1)


if __name__ == "__main__":
    main()
