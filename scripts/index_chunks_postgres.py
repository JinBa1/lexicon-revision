"""Offline indexing: chunk -> embed -> PostgreSQL (pgvector).

Usage:
    python scripts/index_chunks_postgres.py \
        --input local/corpora/cam-cs-tripos/mineru-output/ \
        --collection cam-cs-tripos
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.db.config import create_database_engine, load_database_settings  # noqa: E402
from src.ingestion.indexing import (  # noqa: E402,F401
    build_embedding_text,
    index_collection_postgres,
    validate_manifest_ownership,
)
from src.search.providers.config import (  # noqa: E402
    build_embedding_provider,
    load_retrieval_provider_settings,
)

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
        "--collection-config",
        default=None,
        help="Path to the collection config JSON file",
    )
    parser.add_argument(
        "--university",
        default="cam",
        help="University code used in chunk IDs (default: cam)",
    )
    parser.add_argument(
        "--parser",
        default="cambridge",
        choices=["cambridge", "uoe"],
        help="Content-list parser to use (default: cambridge)",
    )
    parser.add_argument(
        "--recreate-collection",
        action="store_true",
        help="Delete and recreate the collection if it exists",
    )
    return parser.parse_args()


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
                collection_config_path=args.collection_config,
                university=args.university,
                parser_name=args.parser,
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
