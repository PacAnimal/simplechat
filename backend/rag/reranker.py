from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger("simplechat.rag.reranker")

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _get_model():
    from sentence_transformers import CrossEncoder
    logger.info("loading rerank model %r (auto-downloads on first use)", RERANK_MODEL)
    return CrossEncoder(RERANK_MODEL)


def rerank(query: str, docs: list[str], top_n: int) -> list[str]:
    if not docs or len(docs) <= 1:
        return docs[:top_n]
    try:
        model = _get_model()
        scores = model.predict([(query, doc) for doc in docs])
        ranked = sorted(zip(scores, docs), key=lambda x: x[0], reverse=True)
        return [doc for _, doc in ranked[:top_n]]
    except Exception:
        logger.warning("reranking failed — returning pre-rerank order", exc_info=True)
        return docs[:top_n]
