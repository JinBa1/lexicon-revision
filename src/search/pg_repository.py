from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from pgvector.sqlalchemy import Vector as PgVectorType
from sqlalchemy import Engine, Float, and_, bindparam, cast, delete, insert, select
from sqlalchemy.orm import Session
from src.chunking.models import Chunk
from src.db.schema import chunk_embeddings, collections, papers
from src.db.schema import chunks as chunks_table
from src.search.service import CollectionNotFoundError, EmbeddingModelMismatchError


@dataclass(frozen=True)
class PgChunkRow:
    chunk_id: str
    chunk_level: str
    parent_chunk_id: str | None
    sub_question_label: str | None
    text: str
    score: float
    metadata: dict[str, Any]


class PgIndexRepository:
    def __init__(
        self,
        *,
        engine: Engine,
        embedding_model_id: str,
        embedding_dimension: int,
    ) -> None:
        self.engine = engine
        self.embedding_model_id = embedding_model_id
        self.embedding_dimension = embedding_dimension

    def recreate_collection(self, collection_name: str) -> None:
        with Session(self.engine) as session:
            stmt = select(collections.c.id).where(collections.c.name == collection_name)
            result = session.execute(stmt).first()
            if result is None:
                return
            collection_id = result[0]
            paper_stmt = select(papers.c.id).where(
                papers.c.collection_id == collection_id
            )
            paper_ids = [row[0] for row in session.execute(paper_stmt)]
            if paper_ids:
                chunk_stmt = select(chunks_table.c.id).where(
                    chunks_table.c.paper_id.in_(paper_ids)
                )
                chunk_row_ids = [row[0] for row in session.execute(chunk_stmt)]
                if chunk_row_ids:
                    session.execute(
                        delete(chunk_embeddings).where(
                            chunk_embeddings.c.chunk_id.in_(chunk_row_ids)
                        )
                    )
                session.execute(
                    delete(chunks_table).where(chunks_table.c.paper_id.in_(paper_ids))
                )
            session.execute(
                delete(papers).where(papers.c.collection_id == collection_id)
            )
            session.execute(
                delete(collections).where(collections.c.id == collection_id)
            )
            session.commit()

    def index_chunks(
        self,
        *,
        collection_name: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        if len(vectors) != len(chunks):
            raise ValueError(f"Got {len(chunks)} chunks but {len(vectors)} vectors")
        for vector in vectors:
            if len(vector) != self.embedding_dimension:
                raise ValueError(
                    "embedding dimension mismatch: "
                    f"expected {self.embedding_dimension}, got {len(vector)}"
                )

        with Session(self.engine) as session:
            collection_row = _load_collection_row(session, collection_name)
            if collection_row is None:
                collection_id = str(uuid.uuid4())
                session.execute(
                    insert(collections).values(
                        id=collection_id,
                        name=collection_name,
                        embedding_model_id=self.embedding_model_id,
                        embedding_dimension=self.embedding_dimension,
                    )
                )
            else:
                collection_id = str(collection_row.id)
                _validate_collection_settings(
                    collection_name=collection_name,
                    actual_model_id=str(collection_row.embedding_model_id),
                    actual_dimension=int(collection_row.embedding_dimension),
                    expected_model_id=self.embedding_model_id,
                    expected_dimension=self.embedding_dimension,
                )

            pdf_to_paper_id: dict[str, str] = {}
            for chunk in chunks:
                pdf_key = chunk.source_pdf
                if pdf_key not in pdf_to_paper_id:
                    existing = session.execute(
                        select(papers.c.id).where(
                            and_(
                                papers.c.collection_id == collection_id,
                                papers.c.source_pdf == pdf_key,
                            )
                        )
                    ).first()
                    if existing is None:
                        paper_id = str(uuid.uuid4())
                        session.execute(
                            insert(papers).values(
                                id=paper_id,
                                collection_id=collection_id,
                                source_pdf=pdf_key,
                            )
                        )
                    else:
                        paper_id = existing[0]
                    pdf_to_paper_id[pdf_key] = paper_id

            chunk_ids = [chunk.id for chunk in chunks]
            if chunk_ids:
                existing_chunk_rows = session.execute(
                    select(chunks_table.c.id).where(
                        and_(
                            chunks_table.c.collection_id == collection_id,
                            chunks_table.c.chunk_id.in_(chunk_ids),
                        )
                    )
                ).all()
                existing_chunk_row_ids = [row[0] for row in existing_chunk_rows]
                if existing_chunk_row_ids:
                    session.execute(
                        delete(chunk_embeddings).where(
                            chunk_embeddings.c.chunk_id.in_(existing_chunk_row_ids)
                        )
                    )
                    session.execute(
                        delete(chunks_table).where(
                            chunks_table.c.id.in_(existing_chunk_row_ids)
                        )
                    )

            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk_row_id = str(uuid.uuid4())
                session.execute(
                    insert(chunks_table).values(
                        id=chunk_row_id,
                        chunk_id=chunk.id,
                        collection_id=collection_id,
                        paper_id=pdf_to_paper_id[chunk.source_pdf],
                        chunk_level=chunk.chunk_level,
                        parent_chunk_id=chunk.parent_chunk_id,
                        sub_question_label=chunk.sub_question_label,
                        text=chunk.text,
                        year=chunk.year,
                        paper=chunk.paper,
                        question_number=chunk.question_number,
                        topic=chunk.topic,
                        author=chunk.author,
                        tripos_part=chunk.tripos_part,
                        marks=chunk.marks,
                        total_marks=chunk.total_marks,
                        has_code=chunk.has_code,
                        has_figure=chunk.has_figure,
                        has_table=chunk.has_table,
                        source_pdf=chunk.source_pdf,
                    )
                )
                session.execute(
                    insert(chunk_embeddings).values(
                        chunk_id=chunk_row_id,
                        embedding_model_id=self.embedding_model_id,
                        embedding=vector,
                    )
                )

            session.commit()


class PgSearchRepository:
    def __init__(self, *, engine: Engine) -> None:
        self.engine = engine

    def search(
        self,
        *,
        collection_name: str,
        query_vector: list[float],
        embedding_model_id: str,
        embedding_dimension: int,
        filters: dict[str, Any],
        limit: int,
    ) -> list[PgChunkRow]:
        if len(query_vector) != embedding_dimension:
            raise ValueError(
                f"query vector dimension {len(query_vector)} does not match "
                f"expected {embedding_dimension}"
            )
        with Session(self.engine) as session:
            collection_row = _load_collection_row(session, collection_name)
            if collection_row is None:
                raise CollectionNotFoundError(collection_name)
            _validate_collection_settings(
                collection_name=collection_name,
                actual_model_id=str(collection_row.embedding_model_id),
                actual_dimension=int(collection_row.embedding_dimension),
                expected_model_id=embedding_model_id,
                expected_dimension=embedding_dimension,
            )

            vec_param = cast(bindparam("query_vec"), PgVectorType)
            distance_expr = chunk_embeddings.c.embedding.op("<=>", return_type=Float)(
                vec_param
            ).label("distance")

            conditions = [
                chunks_table.c.collection_id == collection_row.id,
                chunk_embeddings.c.embedding_model_id == embedding_model_id,
            ]

            for key, value in filters.items():
                if value is None:
                    continue
                if key == "marks_min":
                    conditions.append(chunks_table.c.marks >= value)
                elif key in (
                    "year",
                    "paper",
                    "question_number",
                    "topic",
                    "has_code",
                    "has_figure",
                    "has_table",
                    "source_pdf",
                    "chunk_level",
                ):
                    conditions.append(getattr(chunks_table.c, key) == value)

            stmt = (
                select(
                    chunks_table.c.chunk_id,
                    chunks_table.c.chunk_level,
                    chunks_table.c.parent_chunk_id,
                    chunks_table.c.sub_question_label,
                    chunks_table.c.text,
                    distance_expr,
                    chunks_table.c.year,
                    chunks_table.c.paper,
                    chunks_table.c.question_number,
                    chunks_table.c.topic,
                    chunks_table.c.author,
                    chunks_table.c.tripos_part,
                    chunks_table.c.marks,
                    chunks_table.c.total_marks,
                    chunks_table.c.has_code,
                    chunks_table.c.has_figure,
                    chunks_table.c.has_table,
                    chunks_table.c.source_pdf,
                )
                .select_from(
                    chunks_table.join(
                        chunk_embeddings,
                        chunks_table.c.id == chunk_embeddings.c.chunk_id,
                    )
                )
                .where(and_(*conditions))
                .order_by(distance_expr, chunks_table.c.chunk_id)
                .limit(limit)
            )
            results = session.execute(
                stmt.params(query_vec=str(query_vector))
            ).fetchall()

            return [
                PgChunkRow(
                    chunk_id=row.chunk_id,
                    chunk_level=row.chunk_level,
                    parent_chunk_id=row.parent_chunk_id,
                    sub_question_label=row.sub_question_label,
                    text=row.text,
                    score=1.0 - row.distance,
                    metadata={
                        "year": row.year,
                        "paper": row.paper,
                        "question_number": row.question_number,
                        "topic": row.topic,
                        "author": row.author,
                        "tripos_part": row.tripos_part,
                        "chunk_level": row.chunk_level,
                        "parent_chunk_id": row.parent_chunk_id,
                        "sub_question_label": row.sub_question_label,
                        "marks": row.marks,
                        "total_marks": row.total_marks,
                        "has_code": row.has_code,
                        "has_figure": row.has_figure,
                        "has_table": row.has_table,
                        "source_pdf": row.source_pdf,
                    },
                )
                for row in results
            ]


def _load_collection_row(session: Session, collection_name: str):
    stmt = select(
        collections.c.id,
        collections.c.embedding_model_id,
        collections.c.embedding_dimension,
    ).where(collections.c.name == collection_name)
    return session.execute(stmt).first()


def _validate_collection_settings(
    *,
    collection_name: str,
    actual_model_id: str,
    actual_dimension: int,
    expected_model_id: str,
    expected_dimension: int,
) -> None:
    if actual_model_id != expected_model_id:
        raise EmbeddingModelMismatchError(
            collection=collection_name,
            expected=expected_model_id,
            actual=actual_model_id,
        )
    if actual_dimension != expected_dimension:
        raise ValueError(
            f"Collection '{collection_name}' was indexed with embedding dimension "
            f"{actual_dimension} but the configured query embedder expects "
            f"{expected_dimension}"
        )
