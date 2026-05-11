"""Tests for hybrid BM25 + semantic RAG store (query_collection)."""
from unittest.mock import MagicMock, patch

import chromadb
import pytest
from chromadb import Documents, EmbeddingFunction, Embeddings


class BagOfWordsEmbedding(EmbeddingFunction):
    """Deterministic BOW embedding over a fixed vocabulary.

    Each document/query is turned into a normalised vector of word-presence
    flags, giving fully predictable cosine distances for testing.
    """
    VOCAB = ["cat", "mat", "sat", "quantum", "physics", "research", "dog"]

    def __init__(self) -> None:
        pass

    def __call__(self, input: Documents) -> Embeddings:
        result = []
        for text in input:
            words = set(text.lower().split())
            vec = [1.0 if w in words else 0.0 for w in self.VOCAB]
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            result.append([v / norm for v in vec])
        return result


def _setup_collection(
    client: chromadb.ClientAPI,
    dataset_id: int,
    docs: list[str],
    embed_fn: EmbeddingFunction,
) -> chromadb.Collection:
    from backend.rag.store import _collection_name
    col = client.get_or_create_collection(
        name=_collection_name(dataset_id),
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    ids = [f"f0_c{i}" for i in range(len(docs))]
    metadatas = [{"file_id": 0, "filename": "test.txt", "chunk": i} for i in range(len(docs))]
    col.add(documents=docs, ids=ids, metadatas=metadatas)
    return col


@pytest.fixture
def eph() -> chromadb.ClientAPI:
    """Fresh ephemeral ChromaDB client per test."""
    return chromadb.EphemeralClient()


# ---------------------------------------------------------------------------
# basic functionality
# ---------------------------------------------------------------------------


def test_basic_returns_results(eph):
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()
    _setup_collection(eph, 1, ["The cat sat on the mat", "Quantum physics research"], embed_fn)

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        results = query_collection(1, embed_fn, "cat mat", n_results=5)

    assert len(results) > 0
    assert any("cat" in r.lower() for r in results)


def test_n_results_limits_output(eph):
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()
    docs = [f"cat mat document {i}" for i in range(10)]
    _setup_collection(eph, 2, docs, embed_fn)

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        results = query_collection(2, embed_fn, "cat mat", n_results=3)

    assert len(results) <= 3


def test_missing_collection_returns_empty():
    from backend.rag.store import query_collection
    eph = chromadb.EphemeralClient()  # no collection created

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        results = query_collection(999, MagicMock(), "anything", n_results=5)

    assert results == []


def test_empty_collection_returns_empty(eph):
    from backend.rag.store import get_or_create_collection, query_collection
    embed_fn = BagOfWordsEmbedding()

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        get_or_create_collection(3, embed_fn)
        results = query_collection(3, embed_fn, "anything", n_results=5)

    assert results == []


# ---------------------------------------------------------------------------
# BM25 keyword boost
# ---------------------------------------------------------------------------


def test_bm25_ranks_keyword_match_first(eph):
    """The doc with exact keyword overlap must rank above one with zero overlap."""
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()
    docs = [
        "The cat sat on the mat",     # full keyword match to query "cat mat"
        "Quantum physics research",   # no keyword overlap
    ]
    _setup_collection(eph, 4, docs, embed_fn)

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        results = query_collection(4, embed_fn, "cat mat", n_results=2)

    assert results, "should return at least one result"
    assert "cat" in results[0].lower(), "keyword-matching doc should be ranked first"


def test_bm25_surfaces_keyword_doc_absent_from_semantic_topk(eph):
    """BM25 can surface a document even if it lands outside the semantic top-k."""
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()

    # Fill with semantically-similar but keyword-unrelated docs, plus one with exact keyword.
    docs = [
        "cat mat sat dog",           # BM25 target — exact keyword "cat mat dog"
    ] + [f"quantum physics paper {i}" for i in range(15)]  # semantic noise
    _setup_collection(eph, 5, docs, embed_fn)

    with patch("backend.rag.store.get_chroma_client", return_value=eph):
        results = query_collection(5, embed_fn, "cat mat dog", n_results=5)

    assert any("cat" in r for r in results), "BM25 should surface the keyword doc"


# ---------------------------------------------------------------------------
# relevance threshold
# ---------------------------------------------------------------------------


def test_threshold_drops_all_when_set_impossibly_high(eph):
    """Patching _MIN_SCORE to > 1 means nothing can ever pass — empty result."""
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()
    _setup_collection(eph, 6, ["cat mat", "quantum research"], embed_fn)

    with (
        patch("backend.rag.store.get_chroma_client", return_value=eph),
        patch("backend.rag.store._MIN_SCORE", 1.1),
    ):
        results = query_collection(6, embed_fn, "cat mat", n_results=5)

    assert results == []


def test_threshold_zero_returns_all_candidates(eph):
    """With _MIN_SCORE = 0 every candidate passes, even poor semantic matches."""
    from backend.rag.store import query_collection
    embed_fn = BagOfWordsEmbedding()
    docs = ["cat mat", "quantum physics"]
    _setup_collection(eph, 7, docs, embed_fn)

    with (
        patch("backend.rag.store.get_chroma_client", return_value=eph),
        patch("backend.rag.store._MIN_SCORE", 0.0),
    ):
        results = query_collection(7, embed_fn, "cat mat", n_results=10)

    assert len(results) == 2, "all docs should pass a zero threshold"
