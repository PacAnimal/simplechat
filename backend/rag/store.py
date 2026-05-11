from __future__ import annotations

import logging
import os

import chromadb
from chromadb import EmbeddingFunction

logger = logging.getLogger("simplechat.rag.store")
_client: chromadb.ClientAPI | None = None

_BM25_WEIGHT = 0.4   # fraction of score from keyword matching; 0.6 goes to semantic
_MIN_SCORE = 0.25    # combined score threshold — chunks below this are dropped


def get_chroma_client(chroma_path: str | None = None) -> chromadb.ClientAPI:
    global _client
    if _client is None:
        if chroma_path is None:
            from ..config import settings
            db_path = settings.database_url.replace("sqlite+aiosqlite:///", "")
            chroma_path = os.path.join(os.path.dirname(os.path.abspath(db_path)), "chroma")
        os.makedirs(chroma_path, exist_ok=True)
        _client = chromadb.PersistentClient(path=chroma_path)
    return _client


def _collection_name(dataset_id: int) -> str:
    return f"ds_{dataset_id}"


def get_or_create_collection(dataset_id: int, embed_fn: EmbeddingFunction) -> chromadb.Collection:
    return get_chroma_client().get_or_create_collection(
        name=_collection_name(dataset_id),
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )


def delete_collection(dataset_id: int) -> None:
    try:
        get_chroma_client().delete_collection(_collection_name(dataset_id))
    except Exception:
        pass


def query_collection(
    dataset_id: int,
    embed_fn: EmbeddingFunction,
    query_text: str,
    n_results: int = 5,
) -> list[str]:
    client = get_chroma_client()
    name = _collection_name(dataset_id)
    try:
        col = client.get_collection(name=name, embedding_function=embed_fn)
    except Exception:
        logger.warning("RAG query: collection %s not found — dataset may not be indexed yet", name)
        return []

    count = col.count()
    if count == 0:
        logger.warning("RAG query: collection %s exists but is empty", name)
        return []

    logger.info("RAG query: collection=%s chunks=%d query=%r", name, count, query_text[:120])

    # fetch all documents for BM25
    all_data = col.get(include=["documents"])
    all_ids: list[str] = all_data["ids"]
    all_texts: list[str] = all_data["documents"]

    # BM25 keyword scores (normalized to [0, 1])
    from rank_bm25 import BM25Okapi
    tokenized = [t.lower().split() for t in all_texts]
    bm25 = BM25Okapi(tokenized)
    raw_bm25 = bm25.get_scores(query_text.lower().split())
    max_bm25 = float(max(raw_bm25)) if any(s > 0 for s in raw_bm25) else 1.0
    bm25_by_id = {doc_id: float(score) / max_bm25 for doc_id, score in zip(all_ids, raw_bm25)}

    # semantic scores via ChromaDB — fetch enough candidates to cover BM25 boosting
    n_semantic = min(max(n_results * 4, 20), count)
    sem_results = col.query(
        query_texts=[query_text],
        n_results=n_semantic,
        include=["documents", "distances"],
    )
    sem_ids: list[str] = sem_results["ids"][0]
    sem_distances: list[float] = sem_results["distances"][0]
    # cosine space: distance = 1 - cosine_similarity, so similarity = 1 - distance
    sem_by_id = {doc_id: max(0.0, 1.0 - dist) for doc_id, dist in zip(sem_ids, sem_distances)}

    # candidate set: union of top-semantic and top-BM25 results
    top_bm25_ids = sorted(bm25_by_id, key=lambda x: bm25_by_id[x], reverse=True)[: n_results * 4]
    candidates = set(sem_ids) | set(top_bm25_ids)

    id_to_text = dict(zip(all_ids, all_texts))
    sem_w = 1.0 - _BM25_WEIGHT

    scored: list[tuple[float, str]] = []
    for doc_id in candidates:
        bm25_s = bm25_by_id.get(doc_id, 0.0)
        sem_s = sem_by_id.get(doc_id, 0.0)
        combined = _BM25_WEIGHT * bm25_s + sem_w * sem_s
        if combined >= _MIN_SCORE:
            scored.append((combined, doc_id))

    scored.sort(reverse=True)
    docs = [id_to_text[doc_id] for _, doc_id in scored[:n_results] if doc_id in id_to_text]

    logger.info("RAG query: returned %d/%d chunk(s) above threshold %.2f", len(docs), len(candidates), _MIN_SCORE)
    if docs:
        logger.debug("RAG first chunk: %s", docs[0][:200])
    return docs
