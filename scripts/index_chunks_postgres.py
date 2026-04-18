"""Offline indexing: chunk -> embed -> PostgreSQL (pgvector).

Usage:
    python scripts/index_chunks_postgres.py \
        --input data/mineru_output/ \
        --collection cam-cs-tripos
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

from scripts.index_chunks import build_embedding_text, build_media_map  # noqa: E402
from sqlalchemy import Engine  # noqa: E402
from src.chunking.pipeline import run_pipeline  # noqa: E402
from src.db.config import create_database_engine, load_database_settings  # noqa: E402
from src.search.pg_repository import PgIndexRepository  # noqa: E402
from src.search.providers.config import (  # noqa: E402
    build_embedding_provider,
    load_retrieval_provider_settings,
)
from src.search.service import DEFAULT_CHROMA_DIR  # noqa: E402

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

    embedding_inputs = [build_embedding_text(chunk) for chunk in chunks]
    result = embedding_model.embed_documents(embedding_inputs)
    vectors = result.vectors

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
    )
    _write_media_sidecar(collection_name=collection_name, chunks=chunks)


def _write_media_sidecar(
    *,
    collection_name: str,
    chunks: list[Any],
    media_dir: str = DEFAULT_CHROMA_DIR,
) -> None:
    media_root = Path(media_dir)
    media_root.mkdir(parents=True, exist_ok=True)
    sidecar_path = media_root / f"{collection_name}_media_map.json"
    sidecar_json = json.dumps(
        build_media_map(chunks),
        indent=2,
        ensure_ascii=False,
    )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=media_root,
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
