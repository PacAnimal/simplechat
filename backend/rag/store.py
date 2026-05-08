from __future__ import annotations

import logging
import os

import chromadb
from chromadb import EmbeddingFunction

logger = logging.getLogger("simplechat.rag.store")
_client: chromadb.ClientAPI | None = None


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
    results = col.query(
        query_texts=[query_text],
        n_results=min(n_results, count),
    )
    docs = results["documents"][0] if results["documents"] else []
    logger.info("RAG query: returned %d chunk(s)", len(docs))
    if docs:
        logger.debug("RAG first chunk: %s", docs[0][:200])
    return docs
