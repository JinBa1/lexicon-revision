from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine
from src.ingestion.conversion import convert_single_pdf
from src.ingestion.indexing import index_collection_postgres
from src.jobs.models import IngestJobMessage
from src.storage.base import ObjectStorage

logger = logging.getLogger(__name__)


class IngestJobHandler:
    """Run one ingest job end-to-end inside a temp workspace."""

    def __init__(
        self,
        *,
        storage: ObjectStorage,
        engine: Engine,
        embedding_model: Any,
        embedding_dimension: int,
        mineru_method: str = "auto",
        mineru_backend: str = "pipeline",
    ) -> None:
        self._storage = storage
        self._engine = engine
        self._embedding_model = embedding_model
        self._embedding_dimension = embedding_dimension
        self._mineru_method = mineru_method
        self._mineru_backend = mineru_backend

    def handle(self, message: IngestJobMessage) -> None:
        pdf_name = Path(message.paper_object_key).name
        if not pdf_name or not pdf_name.lower().endswith(".pdf"):
            raise ValueError(
                f"paper_object_key must end in a PDF filename: "
                f"{message.paper_object_key}"
            )

        started = time.monotonic()
        logger.info(
            "ingest job started",
            extra={"job_id": message.job_id, "collection": message.collection},
        )
        with tempfile.TemporaryDirectory(prefix="ingest_job_") as tmp:
            workspace = Path(tmp)
            pdf_path = workspace / pdf_name
            pdf_path.write_bytes(self._storage.get_bytes(message.paper_object_key))
            output_dir = workspace / "mineru-output"

            convert_single_pdf(
                pdf_path=pdf_path,
                output_dir=output_dir,
                storage=self._storage,
                method=self._mineru_method,
                backend=self._mineru_backend,
            )
            index_collection_postgres(
                mineru_output_dir=str(output_dir),
                collection_name=message.collection,
                engine=self._engine,
                embedding_model=self._embedding_model,
                embedding_dimension=self._embedding_dimension,
                university=message.university,
                parser_name=message.parser,
            )
        logger.info(
            "ingest job finished",
            extra={
                "job_id": message.job_id,
                "collection": message.collection,
                "duration_seconds": round(time.monotonic() - started, 1),
            },
        )
