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
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import Engine  # noqa: E402
from src.chunking.models import Chunk  # noqa: E402
from src.chunking.pipeline import run_pipeline  # noqa: E402
from src.collection_config import load_collection_config  # noqa: E402
from src.db.config import create_database_engine, load_database_settings  # noqa: E402
from src.db.metadata_indexes import ensure_metadata_indexes  # noqa: E402
from src.metadata_schema import (  # noqa: E402
    build_chunk_metadata,
    default_schema_path,
    load_collection_schema,
    render_metadata_summary,
)
from src.search.media_refs import validate_media_refs_by_chunk_id  # noqa: E402
from src.search.media_sidecar import build_storage_media_map  # noqa: E402
from src.search.pg_repository import PgIndexRepository  # noqa: E402
from src.search.providers.config import (  # noqa: E402
    build_embedding_provider,
    load_retrieval_provider_settings,
)
from src.storage import (  # noqa: E402
    ArtifactManifest,
    conversion_run_id_from_stem,
    load_local_manifests,
    mineru_artifact_key,
)

logger = logging.getLogger(__name__)


def build_embedding_text(
    chunk: Chunk,
    *,
    schema: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    parts = [chunk.text.strip()]
    if schema is not None:
        rendered_metadata = render_metadata_summary(schema, metadata or {})
        if rendered_metadata:
            parts.append(rendered_metadata)

    return "\n\n".join(parts)


def validate_manifest_ownership(manifests: dict[str, ArtifactManifest]) -> None:
    for source_pdf, manifest in manifests.items():
        stem = Path(source_pdf).stem
        expected_run_id = conversion_run_id_from_stem(stem)
        if manifest.paper_id != stem:
            raise ValueError(
                f"artifact manifest paper_id mismatch for {source_pdf}: "
                f"expected {stem}, got {manifest.paper_id}"
            )
        if manifest.conversion_run_id != expected_run_id:
            raise ValueError(
                f"artifact manifest conversion_run_id mismatch for {source_pdf}: "
                f"expected {expected_run_id}, got {manifest.conversion_run_id}"
            )
        _validate_manifest_artifact_namespace(
            source_pdf=source_pdf,
            manifest=manifest,
            conversion_run_id=expected_run_id,
        )


def _validate_manifest_artifact_namespace(
    *,
    source_pdf: str,
    manifest: ArtifactManifest,
    conversion_run_id: str,
) -> None:
    image_prefix = f"artifacts/mineru/{conversion_run_id}/images/"
    for artifact in manifest.artifacts:
        if artifact.kind == "content_list":
            expected_key = mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="content_list",
                filename="",
            )
        elif artifact.kind == "markdown":
            expected_key = mineru_artifact_key(
                conversion_run_id=conversion_run_id,
                kind="markdown",
                filename="",
            )
        elif artifact.kind == "image":
            if not artifact.key.startswith(image_prefix):
                raise ValueError(
                    f"artifact manifest image namespace mismatch for {source_pdf}: "
                    f"{artifact.key}"
                )
            image_name = artifact.key.removeprefix(image_prefix)
            if not image_name or "/" in image_name:
                raise ValueError(
                    f"artifact manifest image key is not canonical for "
                    f"{source_pdf}: {artifact.key}"
                )
            continue
        else:
            raise ValueError(
                f"artifact manifest has unsupported artifact kind for "
                f"{source_pdf}: {artifact.kind}"
            )
        if artifact.key != expected_key:
            raise ValueError(
                f"artifact manifest {artifact.kind} key mismatch for {source_pdf}: "
                f"expected {expected_key}, got {artifact.key}"
            )


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


def index_collection_postgres(
    mineru_output_dir: str,
    collection_name: str,
    engine: Engine,
    embedding_model: Any,
    embedding_dimension: int,
    metadata_path: str | None = None,
    metadata_schema_path: str | None = None,
    collection_config_path: str | None = None,
    university: str = "cam",
    parser_name: str = "cambridge",
    recreate_collection: bool = False,
) -> None:
    chunks = run_pipeline(
        mineru_output_dir=mineru_output_dir,
        metadata_path=metadata_path,
        university=university,
        parser=parser_name,
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
    validate_manifest_ownership(manifests)
    raw_media_refs_by_chunk_id = build_storage_media_map(
        chunks=chunks,
        manifests=manifests,
        verify_local_files=True,
    )
    media_refs_by_chunk_id = validate_media_refs_by_chunk_id(
        chunks=chunks,
        media_refs_by_chunk_id=raw_media_refs_by_chunk_id,
    )

    schema_path = metadata_schema_path or default_schema_path(collection_name)
    metadata_schema = load_collection_schema(schema_path)
    collection_config = load_collection_config(
        collection_name,
        config_path=collection_config_path,
    )
    chunk_metadata = [build_chunk_metadata(chunk, metadata_schema) for chunk in chunks]
    embedding_inputs = [
        build_embedding_text(chunk, schema=metadata_schema, metadata=metadata)
        for chunk, metadata in zip(chunks, chunk_metadata, strict=True)
    ]
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
        metadata_schema=metadata_schema,
        community_id=collection_config.community_id,
        media_refs_by_chunk_id=media_refs_by_chunk_id,
    )
    ensure_metadata_indexes(
        engine,
        collection_name=collection_name,
        schema=metadata_schema,
    )


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
