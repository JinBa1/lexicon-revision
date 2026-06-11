"""Ingestion worker entrypoint: python -m src.worker."""

from __future__ import annotations

import logging
import os
import threading

from src.db.config import create_database_engine, load_database_settings
from src.jobs.config import build_ingest_job_queue, load_ingest_queue_settings
from src.runtime.config import validate_worker_production_profile
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
    if queue_settings.provider == "none":
        raise SystemExit(
            "worker requires INGEST_QUEUE_PROVIDER=sqs (or memory for local dev)"
        )

    environment_raw = os.environ.get("APP_ENV", "dev").lower()
    if environment_raw not in ("dev", "test", "prod"):
        raise SystemExit(f"Invalid APP_ENV: {environment_raw}")
    from src.runtime.config import Environment

    environment: Environment = environment_raw  # type: ignore[assignment]
    storage_settings = load_object_storage_settings()
    retrieval_settings = load_retrieval_provider_settings()
    try:
        validate_worker_production_profile(
            environment=environment,
            retrieval_settings=retrieval_settings,
            storage_settings=storage_settings,
            ingest_queue_settings=queue_settings,
        )
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    queue = build_ingest_job_queue(queue_settings)
    if queue is None:
        raise SystemExit(
            "worker requires INGEST_QUEUE_PROVIDER=sqs (or memory for local dev)"
        )

    db_settings = load_database_settings()
    engine = create_database_engine(db_settings)
    storage = build_object_storage(storage_settings)
    embedding_model = build_embedding_provider(retrieval_settings)

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
