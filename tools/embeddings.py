from __future__ import annotations
"""Shared embedding utilities used by catalog search and policy RAG."""

import numpy as np
from sentence_transformers import SentenceTransformer
import faiss

_model = None
_embed_cache: dict[str, np.ndarray] = {}


def get_embedding_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def embed_texts(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()
    results = []
    uncached = []
    uncached_idx = []
    for i, t in enumerate(texts):
        if t in _embed_cache:
            results.append(_embed_cache[t])
        else:
            results.append(None)
            uncached.append(t)
            uncached_idx.append(i)
    if uncached:
        new_embeddings = model.encode(uncached, normalize_embeddings=True)
        for i, (text, emb) in enumerate(zip(uncached, new_embeddings)):
            arr = np.array(emb, dtype=np.float32)
            _embed_cache[text] = arr
            results[uncached_idx[i]] = arr
    return np.array(results, dtype=np.float32)


def build_faiss_index(embeddings: np.ndarray) -> faiss.IndexFlatIP:
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    return index


def search_index(index: faiss.IndexFlatIP, query: str, top_k: int = 5) -> list[tuple[int, float]]:
    query_embedding = embed_texts([query])
    scores, indices = index.search(query_embedding, top_k)
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx != -1:
            results.append((int(idx), float(score)))
    return results
