import logging

import httpx
from chromadb import Documents, EmbeddingFunction, Embeddings

logger = logging.getLogger("simplechat.rag.embedder")

EMBED_MODEL = "nomic-embed-text"


class OllamaEmbeddingFunction(EmbeddingFunction):
    def __init__(self, base_url: str, model: str = EMBED_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        resp = httpx.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model, "input": list(input)},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["embeddings"]


async def ensure_embed_model(base_url: str, model: str = EMBED_MODEL) -> None:
    """Pull the embedding model into Ollama if not already present."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.get(f"{base_url}/api/tags")
            names = [m["name"].split(":")[0] for m in r.json().get("models", [])]
            if model in names:
                logger.info("embed model %r already present in Ollama", model)
                return
        except Exception:
            logger.warning("could not reach Ollama at %s — skipping embed model pull", base_url)
            return
    logger.info("pulling embed model %r into Ollama (this may take a moment)…", model)
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            async with client.stream("POST", f"{base_url}/api/pull", json={"name": model}) as r:
                async for _ in r.aiter_lines():
                    pass
        logger.info("embed model %r ready", model)
    except Exception:
        logger.warning("failed to pull embed model %r", model, exc_info=True)
