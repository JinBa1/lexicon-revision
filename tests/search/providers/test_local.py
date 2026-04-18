from src.search.providers.local import (
    LocalCrossEncoderReranker,
    LocalSentenceTransformerEmbedder,
)


class FakeArray:
    def __init__(self, data):
        self.data = data

    def tolist(self):
        return self.data


class FakeSentenceTransformer:
    def __init__(self):
        self.call_count = 0
        self.last_texts = None

    def encode(self, texts, show_progress_bar=True):
        self.call_count += 1
        self.last_texts = texts
        if isinstance(texts, str):
            return FakeArray([0.1, 0.2, 0.3])
        return FakeArray([[float(i), float(i), float(i)] for i in range(len(texts))])


class FakeCrossEncoder:
    def __init__(self):
        self.call_count = 0
        self.last_pairs = None

    def predict(self, pairs):
        self.call_count += 1
        self.last_pairs = pairs
        return FakeArray([float(len(doc)) for _, doc in pairs])


def test_embedder_embed_documents_preserves_order():
    model = FakeSentenceTransformer()
    embedder = LocalSentenceTransformerEmbedder(model=model, model_id="test-model")

    docs = ["doc0", "doc1", "doc2"]
    result = embedder.embed_documents(docs)

    assert model.call_count == 1
    assert model.last_texts == docs
    assert result.vectors == [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]
    assert result.model_id == "test-model"


def test_embedder_embed_documents_empty():
    model = FakeSentenceTransformer()
    embedder = LocalSentenceTransformerEmbedder(model=model, model_id="test-model")

    result = embedder.embed_documents([])

    assert model.call_count == 0
    assert result.vectors == []


def test_embedder_embed_query_exactly_one_vector():
    model = FakeSentenceTransformer()
    embedder = LocalSentenceTransformerEmbedder(model=model, model_id="test-model")

    result = embedder.embed_query("query")

    assert model.call_count == 1
    assert model.last_texts == "query"
    assert result.vectors == [[0.1, 0.2, 0.3]]
    assert result.model_id == "test-model"


def test_reranker_rerank_preserves_order():
    model = FakeCrossEncoder()
    reranker = LocalCrossEncoderReranker(model=model, model_id="test-reranker")

    docs = ["a", "abc", "ab"]
    result = reranker.rerank("query", docs)

    assert model.call_count == 1
    assert model.last_pairs == [("query", "a"), ("query", "abc"), ("query", "ab")]
    assert result.scores == [1.0, 3.0, 2.0]
    assert result.model_id == "test-reranker"


def test_reranker_rerank_empty():
    model = FakeCrossEncoder()
    reranker = LocalCrossEncoderReranker(model=model, model_id="test-reranker")

    result = reranker.rerank("query", [])

    assert model.call_count == 0
    assert result.scores == []
