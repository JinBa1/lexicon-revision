"""Ingestion worker entrypoint: python -m src.worker."""

from __future__ import annotations

import logging
import os
import threading

from src.db.config import create_database_engine, load_database_settings
from src.jobs.config import build_ingest_job_queue, load_ingest_queue_settings
from src.search.providers.config import (
    build_embedding_provider,
    load_retrieval_provider_settings,
)
from src.storage import build_object_storage, load_object_storage_settings
from src.worker.handler import IngestJobHandler
from src.worker.logging import configure_json_logging
from src.worker.runner import install_sigterm_handler, run_worker

logger = logging.getLogger(__name__)


def main() -> None:
    configure_json_logging()

    queue_settings = load_ingest_queue_settings()
    if (
        os.environ.get("APP_ENV", "dev").lower() == "prod"
        and queue_settings.provider == "memory"
    ):
        raise SystemExit("memory ingest queue is not allowed in prod")
    queue = build_ingest_job_queue(queue_settings)
    if queue is None:
        raise SystemExit(
            "worker requires INGEST_QUEUE_PROVIDER=sqs (or memory for local dev)"
        )

    db_settings = load_database_settings()
    engine = create_database_engine(db_settings)
    storage = build_object_storage(load_object_storage_settings())
    embedding_model = build_embedding_provider(load_retrieval_provider_settings())

    handler = IngestJobHandler(
        storage=storage,
        engine=engine,
        embedding_model=embedding_model,
        embedding_dimension=db_settings.embedding_dimension,
        mineru_method=os.environ.get("INGEST_MINERU_METHOD", "auto"),
        mineru_backend=os.environ.get("INGEST_MINERU_BACKEND", "pipeline"),
    )

    stop_event = threading.Event()
    install_sigterm_handler(stop_event)
    logger.info(
        "ingestion worker started",
        extra={"queue_provider": queue_settings.provider},
    )
    try:
        run_worker(queue=queue, handler=handler, stop_event=stop_event)
    finally:
        close = getattr(embedding_model, "close", None)
        if callable(close):
            close()
        engine.dispose()
        logger.info("ingestion worker stopped")


if __name__ == "__main__":
    main()
