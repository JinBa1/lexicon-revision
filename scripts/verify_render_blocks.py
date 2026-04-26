"""Verify that a collection's chunks all carry render_blocks."""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pydantic import TypeAdapter, ValidationError  # noqa: E402
from sqlalchemy import text  # noqa: E402
from src.db.config import create_database_engine, load_database_settings  # noqa: E402
from src.rendering.blocks import RenderBlock  # noqa: E402

logger = logging.getLogger("verify_render_blocks")
RENDER_BLOCKS_ADAPTER = TypeAdapter(list[RenderBlock])


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    parser = argparse.ArgumentParser(
        description="Verify a collection's chunks have render_blocks.",
    )
    parser.add_argument("--collection", required=True)
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL override. Defaults to DATABASE_URL settings.",
    )
    args = parser.parse_args(argv)

    settings = load_database_settings()
    if args.database_url:
        settings = replace(settings, database_url=args.database_url)

    engine = create_database_engine(settings)
    failures: list[str] = []
    rows = []

    try:
        with engine.connect() as conn:
            collection_id = conn.execute(
                text("SELECT id FROM collections WHERE name = :name"),
                {"name": args.collection},
            ).scalar_one_or_none()
            if collection_id is None:
                logger.error("collection not found: %s", args.collection)
                return 1

            total = conn.execute(
                text(
                    """
                    SELECT count(*)
                    FROM chunks
                    WHERE collection_id = :collection_id
                    """
                ),
                {"collection_id": collection_id},
            ).scalar_one()
            logger.info("chunks total: %d", total)

            null_count = conn.execute(
                text(
                    """
                    SELECT count(*)
                    FROM chunks
                    WHERE collection_id = :collection_id
                      AND render_blocks IS NULL
                    """
                ),
                {"collection_id": collection_id},
            ).scalar_one()
            if null_count > 0:
                failures.append(f"{null_count} chunks have render_blocks IS NULL")

            empty_with_text = conn.execute(
                text(
                    """
                    SELECT chunk_id
                    FROM chunks
                    WHERE collection_id = :collection_id
                      AND length(btrim(text)) > 0
                      AND (
                        render_blocks IS NULL
                        OR jsonb_typeof(render_blocks) != 'array'
                        OR jsonb_array_length(render_blocks) = 0
                      )
                    ORDER BY chunk_id
                    LIMIT 5
                    """
                ),
                {"collection_id": collection_id},
            ).fetchall()
            if empty_with_text:
                sample = ", ".join(row.chunk_id for row in empty_with_text)
                failures.append(
                    "chunks with non-empty text have NULL or empty render_blocks "
                    f"(sample): {sample}"
                )

            rows = conn.execute(
                text(
                    """
                    SELECT chunk_id, render_blocks
                    FROM chunks
                    WHERE collection_id = :collection_id
                      AND render_blocks IS NOT NULL
                    ORDER BY chunk_id
                    """
                ),
                {"collection_id": collection_id},
            ).fetchall()
    finally:
        engine.dispose()

    for row in rows:
        failures.extend(_shape_failures(row.chunk_id, row.render_blocks))

    if failures:
        for failure in failures:
            logger.error("FAIL: %s", failure)
        return 1

    logger.info("OK: all checks pass")
    return 0


def _shape_failures(chunk_id: str, render_blocks: Any) -> list[str]:
    if not isinstance(render_blocks, list):
        return [f"chunk {chunk_id}: render_blocks is not an array"]

    failures: list[str] = []
    try:
        RENDER_BLOCKS_ADAPTER.validate_python(render_blocks)
    except ValidationError as exc:
        failures.append(f"chunk {chunk_id}: schema validation failed: {exc}")

    for index, block in enumerate(render_blocks):
        if not isinstance(block, dict):
            failures.append(f"chunk {chunk_id}: block {index} is not an object")
            continue

        block_type = block.get("type")
        if block_type == "image" and not block.get("media_id"):
            failures.append(f"chunk {chunk_id}: image block missing media_id")
        if block_type == "table" and not _has_rows(block):
            failures.append(f"chunk {chunk_id}: table block missing rows")

    return failures


def _has_rows(block: dict[str, Any]) -> bool:
    rows = block.get("rows")
    return isinstance(rows, list) and len(rows) > 0


if __name__ == "__main__":
    raise SystemExit(main())
