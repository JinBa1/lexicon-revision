from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.search.errors import InvalidMetadataFilterError
from src.search.pg_repository import PgSearchRepository


def _schema() -> CollectionMetadataSchema:
    return CollectionMetadataSchema.model_validate(
        {
            "version": 1,
            "fields": [
                {
                    "key": "year",
                    "label": "Year",
                    "type": "integer",
                    "operators": ["eq", "gte", "lte"],
                    "exposed": True,
                }
            ],
        }
    )


class _EmptyExecuteResult:
    def fetchall(self) -> list[object]:
        return []


class _FakeSession:
    def __init__(self, engine) -> None:
        del engine

    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def execute(self, stmt):
        del stmt
        return _EmptyExecuteResult()


def test_pg_search_repository_validates_filters_when_called_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PgSearchRepository(engine=Mock())

    monkeypatch.setattr("src.search.pg_repository.Session", _FakeSession)
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_row",
        lambda session, collection_name: SimpleNamespace(
            id="collection-id",
            embedding_model_id="fake-v1",
            embedding_dimension=2,
            metadata_schema={"version": 1, "fields": []},
        ),
    )
    monkeypatch.setattr(
        "src.search.pg_repository._validate_collection_settings",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_schema",
        lambda **kwargs: _schema(),
    )
    monkeypatch.setattr(
        "src.search.pg_repository.validate_filter_conditions",
        lambda filters, schema: (_ for _ in ()).throw(
            InvalidMetadataFilterError("invalid direct call")
        ),
    )

    with pytest.raises(InvalidMetadataFilterError, match="invalid direct call"):
        repository.search(
            collection_name="fixture",
            query_vector=[1.0, 0.0],
            embedding_model_id="fake-v1",
            embedding_dimension=2,
            filters=[FilterCondition(field="topic", op="eq", value="Algorithms")],
            limit=5,
        )


def test_pg_search_repository_allows_structural_filters_outside_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PgSearchRepository(engine=Mock())

    monkeypatch.setattr("src.search.pg_repository.Session", _FakeSession)
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_row",
        lambda session, collection_name: SimpleNamespace(
            id="collection-id",
            embedding_model_id="fake-v1",
            embedding_dimension=2,
            metadata_schema={"version": 1, "fields": []},
        ),
    )
    monkeypatch.setattr(
        "src.search.pg_repository._validate_collection_settings",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_schema",
        lambda **kwargs: _schema(),
    )

    results = repository.search(
        collection_name="fixture",
        query_vector=[1.0, 0.0],
        embedding_model_id="fake-v1",
        embedding_dimension=2,
        filters=[
            FilterCondition(field="source_pdf", op="eq", value="fixture.pdf"),
            FilterCondition(field="chunk_level", op="eq", value="question"),
        ],
        limit=5,
    )

    assert results == []


def test_pg_search_repository_rejects_invalid_structural_filter_operator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = PgSearchRepository(engine=Mock())

    monkeypatch.setattr("src.search.pg_repository.Session", _FakeSession)
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_row",
        lambda session, collection_name: SimpleNamespace(
            id="collection-id",
            embedding_model_id="fake-v1",
            embedding_dimension=2,
            metadata_schema={"version": 1, "fields": []},
        ),
    )
    monkeypatch.setattr(
        "src.search.pg_repository._validate_collection_settings",
        lambda **kwargs: None,
    )
    monkeypatch.setattr(
        "src.search.pg_repository._load_collection_schema",
        lambda **kwargs: _schema(),
    )

    with pytest.raises(
        InvalidMetadataFilterError,
        match="does not allow operator 'gte'",
    ):
        repository.search(
            collection_name="fixture",
            query_vector=[1.0, 0.0],
            embedding_model_id="fake-v1",
            embedding_dimension=2,
            filters=[
                FilterCondition(
                    field="source_pdf",
                    op="gte",
                    value="fixture.pdf",
                )
            ],
            limit=5,
        )
