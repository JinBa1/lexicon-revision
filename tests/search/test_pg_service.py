from __future__ import annotations

import inspect
from unittest.mock import Mock

import pytest
from src.metadata_schema.models import CollectionMetadataSchema, FilterCondition
from src.runtime.telemetry import TokenUsage
from src.search.errors import DEFAULT_COLLECTION, CollectionNotFoundError
from src.search.models import SearchResponse
from src.search.pg_repository import CollectionRetrievalThresholds, PgChunkRow
from src.search.pg_service import PgSearchService
from src.search.providers.base import EmbeddingResult, RerankResult
from src.storage.local import LocalObjectStorage

SECRET = b"pg-search-secret"
MEDIA_OBJECT_KEY = "artifacts/mineru/run-y2023p2q5/images/fig-1.png"


class _Embedder:
    model_id = "fake-v1"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[1.0, 0.0] for _ in texts],
            model_id=self.model_id,
            provider="voyage",
            latency_ms=9,
            usage=TokenUsage(total_tokens=4),
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[1.0, 0.0]],
            model_id=self.model_id,
            provider="voyage",
            latency_ms=12,
            usage=TokenUsage(total_tokens=5),
        )

    def health(self) -> str:
        return "ok"


class _Repo:
    def __init__(
        self,
        thresholds: dict[str, CollectionRetrievalThresholds] | None = None,
    ) -> None:
        self.calls = []
        self.thresholds = thresholds or {}

    def get_collection_retrieval_thresholds(
        self,
        collection_name: str,
    ) -> CollectionRetrievalThresholds:
        self.calls.append({"threshold_collection_name": collection_name})
        return self.thresholds.get(
            collection_name,
            CollectionRetrievalThresholds(
                vector_min_score=None,
                rerank_min_score=None,
            ),
        )

    def get_collection_schema(self, collection_name: str) -> CollectionMetadataSchema:
        self.calls.append({"schema_collection_name": collection_name})
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

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return [
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="body",
                score=0.9,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "x.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            )
        ]


class _FlakySearchRepo(_Repo):
    def __init__(self) -> None:
        super().__init__()
        self.fail_search = False

    def search(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_search:
            raise RuntimeError("search failed")
        return super().search(**kwargs)


def test_pg_search_service_returns_search_response() -> None:
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=3,
        rerank=False,
    )

    assert isinstance(response, SearchResponse)
    assert response.results[0].chunk_id == "cam-1"
    assert repo.calls[1]["embedding_model_id"] == "fake-v1"
    assert repo.calls[1]["embedding_dimension"] == 2
    telemetry = service.pop_last_execution_telemetry()
    assert telemetry is not None
    assert telemetry.embedding.provider == "voyage"
    assert telemetry.embedding.model == "fake-v1"
    assert telemetry.embedding.usage == TokenUsage(total_tokens=5)
    assert telemetry.rerank is None


def test_pg_search_service_includes_render_blocks_from_rows() -> None:
    render_blocks = [{"type": "paragraph", "runs": [{"type": "text", "text": "body"}]}]
    repo = _Repo()
    repo.search = Mock(
        return_value=[
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="body",
                score=0.9,
                metadata={},
                render_blocks=render_blocks,
            )
        ]
    )
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=3,
        rerank=False,
    )

    assert response.results[0].model_dump(mode="json")["render_blocks"] == render_blocks


def test_pg_search_service_uses_default_collection_constant() -> None:
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    service.search("q", filters=[], limit=3, rerank=False)

    assert repo.calls[1]["collection_name"] == DEFAULT_COLLECTION


def test_pg_search_service_materializes_media_from_row_refs(tmp_path) -> None:
    storage = LocalObjectStorage(
        root=tmp_path / "object-store",
        dev_presign_secret=SECRET,
    )
    storage.put_bytes(
        key=MEDIA_OBJECT_KEY,
        data=b"png",
        content_type="image/png",
    )
    repo = _Repo()
    repo.search = Mock(
        return_value=[
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="body",
                score=0.9,
                metadata={},
                media_refs=[
                    {
                        "media_id": "fig-1",
                        "kind": "image",
                        "object_key": MEDIA_OBJECT_KEY,
                        "relation": "direct",
                    }
                ],
            )
        ]
    )
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
        object_storage=storage,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=3,
        rerank=False,
    )

    assert response.results[0].media[0].media_id == "fig-1"
    assert response.results[0].media[0].object_key == MEDIA_OBJECT_KEY
    assert response.results[0].media[0].access_url is not None


def test_pg_search_service_constructor_has_no_media_dir_parameter() -> None:
    signature = inspect.signature(PgSearchService)

    assert "media_dir" not in signature.parameters


class _Reranker:
    model_id = "fake-rerank"

    def rerank(self, query: str, documents: list[str]) -> RerankResult:
        return RerankResult(
            scores=[2.0, 1.0],
            model_id=self.model_id,
            provider="voyage",
            latency_ms=8,
            usage=TokenUsage(total_tokens=3),
        )

    def health(self) -> str:
        return "ok"


class _TwoRowRepo:
    def __init__(
        self,
        thresholds: dict[str, CollectionRetrievalThresholds] | None = None,
    ) -> None:
        self.thresholds = thresholds or {}

    def get_collection_retrieval_thresholds(
        self,
        collection_name: str,
    ) -> CollectionRetrievalThresholds:
        return self.thresholds.get(
            collection_name,
            CollectionRetrievalThresholds(
                vector_min_score=None,
                rerank_min_score=None,
            ),
        )

    def get_collection_schema(self, collection_name: str) -> CollectionMetadataSchema:
        del collection_name
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

    def search(self, **kwargs):
        return [
            PgChunkRow(
                chunk_id="cam-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="first",
                score=0.1,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "x.pdf",
                },
            ),
            PgChunkRow(
                chunk_id="cam-2",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="second",
                score=0.2,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "y.pdf",
                },
            ),
        ]


def test_pg_search_service_applies_rerank_order() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=_Reranker(),
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=2,
        rerank=True,
    )

    assert [result.chunk_id for result in response.results] == ["cam-1", "cam-2"]
    assert response.results[0].score == 2.0


def test_pg_search_service_filters_vector_results_using_collection_min_score() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(
            thresholds={
                "fixture": CollectionRetrievalThresholds(
                    vector_min_score=0.15,
                    rerank_min_score=None,
                )
            }
        ),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=2,
        rerank=False,
    )

    assert [result.chunk_id for result in response.results] == ["cam-2"]
    assert response.total == 1


def test_pg_search_service_filters_after_rerank_using_collection_min_score() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(
            thresholds={
                "fixture": CollectionRetrievalThresholds(
                    vector_min_score=0.95,
                    rerank_min_score=1.5,
                )
            }
        ),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=_Reranker(),
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=2,
        rerank=True,
    )

    assert [result.chunk_id for result in response.results] == ["cam-1"]
    assert response.results[0].score == 2.0
    telemetry = service.pop_last_execution_telemetry()
    assert telemetry is not None
    assert telemetry.rerank is not None


def test_pg_search_service_skips_filtering_when_collection_threshold_is_null() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(
            thresholds={
                "fixture": CollectionRetrievalThresholds(
                    vector_min_score=None,
                    rerank_min_score=None,
                )
            }
        ),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=2,
        rerank=False,
    )

    assert [result.chunk_id for result in response.results] == ["cam-1", "cam-2"]
    assert response.total == 2


@pytest.mark.parametrize(
    ("thresholds", "reranker", "rerank", "expected_column"),
    [
        (
            CollectionRetrievalThresholds(
                vector_min_score=float("inf"),
                rerank_min_score=None,
            ),
            None,
            False,
            "collections.retrieval_vector_min_score",
        ),
        (
            CollectionRetrievalThresholds(
                vector_min_score=None,
                rerank_min_score=float("inf"),
            ),
            _Reranker(),
            True,
            "collections.retrieval_rerank_min_score",
        ),
    ],
)
def test_pg_search_service_rejects_non_finite_collection_threshold_with_context(
    thresholds: CollectionRetrievalThresholds,
    reranker: _Reranker | None,
    rerank: bool,
    expected_column: str,
) -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(thresholds={"fixture": thresholds}),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=reranker,
    )

    with pytest.raises(ValueError) as exc_info:
        service.search(
            "q",
            collection="fixture",
            filters=[],
            limit=2,
            rerank=rerank,
        )

    message = str(exc_info.value)
    assert expected_column in message
    assert "'fixture'" in message
    assert "must be finite" in message


def test_pg_search_service_thresholds_are_collection_scoped() -> None:
    service = PgSearchService(
        repository=_TwoRowRepo(
            thresholds={
                "strict-fixture": CollectionRetrievalThresholds(
                    vector_min_score=0.95,
                    rerank_min_score=None,
                ),
                "loose-fixture": CollectionRetrievalThresholds(
                    vector_min_score=0.0,
                    rerank_min_score=None,
                ),
            }
        ),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    strict_response = service.search(
        "q",
        collection="strict-fixture",
        filters=[],
        limit=2,
        rerank=False,
    )
    loose_response = service.search(
        "q",
        collection="loose-fixture",
        filters=[],
        limit=2,
        rerank=False,
    )

    assert strict_response.results == []
    assert [result.chunk_id for result in loose_response.results] == [
        "cam-1",
        "cam-2",
    ]


class _ThresholdFailingTwoRowRepo(_TwoRowRepo):
    def get_collection_retrieval_thresholds(
        self,
        collection_name: str,
    ) -> CollectionRetrievalThresholds:
        raise AssertionError("threshold lookup should be disabled")


def test_pg_search_service_can_disable_collection_thresholds() -> None:
    service = PgSearchService(
        repository=_ThresholdFailingTwoRowRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
        apply_collection_thresholds=False,
    )

    response = service.search(
        "q",
        collection="fixture",
        filters=[],
        limit=2,
        rerank=False,
    )

    assert [result.chunk_id for result in response.results] == ["cam-1", "cam-2"]
    assert response.total == 2


class _MissingCollectionRepo:
    def get_collection_schema(self, collection_name: str) -> CollectionMetadataSchema:
        raise CollectionNotFoundError(collection_name)

    def search(self, **kwargs):
        raise CollectionNotFoundError("missing")


def test_pg_search_service_propagates_missing_collection() -> None:
    service = PgSearchService(
        repository=_MissingCollectionRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    with pytest.raises(CollectionNotFoundError, match="missing"):
        service.search("q", collection="missing", filters=[], limit=2, rerank=False)


def test_pg_search_service_clears_stale_telemetry_when_search_fails() -> None:
    repo = _FlakySearchRepo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )

    service.search("q", collection="fixture", filters=[], limit=2, rerank=False)
    repo.fail_search = True

    with pytest.raises(RuntimeError, match="search failed"):
        service.search("q", collection="fixture", filters=[], limit=2, rerank=False)

    assert service.pop_last_execution_telemetry() is None


class _EmbedderAlt:
    model_id = "fake-v2"

    def embed_documents(self, texts: list[str]) -> EmbeddingResult:
        del texts
        return EmbeddingResult(
            vectors=[[0.0, 1.0]],
            model_id=self.model_id,
            provider="openai",
            latency_ms=4,
            usage=TokenUsage(total_tokens=2),
        )

    def embed_query(self, text: str) -> EmbeddingResult:
        del text
        return EmbeddingResult(
            vectors=[[0.0, 1.0]],
            model_id=self.model_id,
            provider="openai",
            latency_ms=6,
            usage=TokenUsage(total_tokens=3),
        )

    def health(self) -> str:
        return "ok"


def test_pg_search_service_telemetry_is_scoped_per_instance() -> None:
    first = PgSearchService(
        repository=_Repo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )
    second = PgSearchService(
        repository=_Repo(),
        embedding_model=_EmbedderAlt(),
        embedding_dimension=2,
        reranker=None,
    )

    first.search("first", collection="fixture", filters=[], limit=2, rerank=False)
    second.search("second", collection="fixture", filters=[], limit=2, rerank=False)

    first_telemetry = first.pop_last_execution_telemetry()
    second_telemetry = second.pop_last_execution_telemetry()

    assert first_telemetry is not None
    assert second_telemetry is not None
    assert first_telemetry.embedding.model == "fake-v1"
    assert second_telemetry.embedding.model == "fake-v2"


class _InvalidChunkLevelRepo:
    def get_collection_retrieval_thresholds(
        self,
        collection_name: str,
    ) -> CollectionRetrievalThresholds:
        del collection_name
        return CollectionRetrievalThresholds(
            vector_min_score=None,
            rerank_min_score=None,
        )

    def get_collection_schema(self, collection_name: str) -> CollectionMetadataSchema:
        del collection_name
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

    def search(self, **kwargs):
        return [
            PgChunkRow(
                chunk_id="bad-1",
                chunk_level="part",
                parent_chunk_id=None,
                sub_question_label=None,
                text="bad row",
                score=0.8,
                metadata={
                    "chunk_level": "part",
                    "source_pdf": "bad.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            ),
            PgChunkRow(
                chunk_id="good-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="good row",
                score=0.7,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "good.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            ),
        ]


class _InvalidChunkLevelWithEnoughValidRepo:
    def get_collection_retrieval_thresholds(
        self,
        collection_name: str,
    ) -> CollectionRetrievalThresholds:
        del collection_name
        return CollectionRetrievalThresholds(
            vector_min_score=None,
            rerank_min_score=None,
        )

    def get_collection_schema(self, collection_name: str) -> CollectionMetadataSchema:
        del collection_name
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

    def search(self, **kwargs):
        return [
            PgChunkRow(
                chunk_id="bad-1",
                chunk_level="part",
                parent_chunk_id=None,
                sub_question_label=None,
                text="bad row",
                score=0.9,
                metadata={
                    "chunk_level": "part",
                    "source_pdf": "bad.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            ),
            PgChunkRow(
                chunk_id="good-1",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="good row 1",
                score=0.8,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "good1.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            ),
            PgChunkRow(
                chunk_id="good-2",
                chunk_level="question",
                parent_chunk_id=None,
                sub_question_label=None,
                text="good row 2",
                score=0.7,
                metadata={
                    "chunk_level": "question",
                    "source_pdf": "good2.pdf",
                    "has_code": False,
                    "has_figure": False,
                    "has_table": False,
                },
            ),
        ]


def test_pg_search_service_skips_invalid_chunk_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_mock = Mock()
    service = PgSearchService(
        repository=_InvalidChunkLevelRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )
    monkeypatch.setattr("src.search.pg_service.logger.warning", warning_mock)

    response = service.search("q", collection="fixture", filters=[], limit=5)

    assert [result.chunk_id for result in response.results] == ["good-1"]
    warning_mock.assert_called_once()
    assert "chunk_level" in warning_mock.call_args.args[0]


def test_pg_search_service_invalid_rows_do_not_consume_limit_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warning_mock = Mock()
    service = PgSearchService(
        repository=_InvalidChunkLevelWithEnoughValidRepo(),
        embedding_model=_Embedder(),
        embedding_dimension=2,
        reranker=None,
    )
    monkeypatch.setattr("src.search.pg_service.logger.warning", warning_mock)

    response = service.search("q", collection="fixture", filters=[], limit=2)

    assert [result.chunk_id for result in response.results] == ["good-1", "good-2"]
    assert response.total == 2
    warning_mock.assert_called_once()


def test_pg_service_passes_filter_conditions_to_repository() -> None:
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
    )

    service.search(
        query="algorithms",
        collection="cam-cs-tripos-fixture",
        filters=[
            FilterCondition(field="year", op="gte", value=2020),
            FilterCondition(field="year", op="lte", value=2024),
        ],
        limit=5,
        rerank=False,
    )

    assert [item.model_dump() for item in repo.calls[1]["filters"]] == [
        {"field": "year", "op": "gte", "value": 2020},
        {"field": "year", "op": "lte", "value": 2024},
    ]


def test_pg_service_reuses_cached_collection_schema() -> None:
    repo = _Repo()
    service = PgSearchService(
        repository=repo,
        embedding_model=_Embedder(),
        embedding_dimension=2,
    )

    schema = service.get_collection_schema("cam-cs-tripos-fixture")
    response = service.search(
        query="algorithms",
        collection="cam-cs-tripos-fixture",
        filters=[],
        limit=5,
        rerank=False,
    )

    assert schema.version == 1
    assert response.collection == "cam-cs-tripos-fixture"
    assert repo.calls.count({"schema_collection_name": "cam-cs-tripos-fixture"}) == 1
