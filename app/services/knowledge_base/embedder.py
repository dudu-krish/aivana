"""Embedding provider for knowledge base vectors."""

from __future__ import annotations

import hashlib
import math

import httpx

from app.config import settings


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    api_key = (settings.openai_api_key or "").strip()
    if api_key:
        return _openai_embed(texts, api_key)
    return [_hash_embed(t) for t in texts]


def _openai_embed(texts: list[str], api_key: str) -> list[list[float]]:
    response = httpx.post(
        f"{settings.openai_base_url.rstrip('/')}/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": settings.kb_embedding_model, "input": texts},
        timeout=90.0,
    )
    response.raise_for_status()
    data = sorted(response.json()["data"], key=lambda row: row["index"])
    return [row["embedding"] for row in data]


def _hash_embed(text: str, dim: int = 384) -> list[float]:
    """Deterministic fallback when OpenAI is not configured."""
    vec = [0.0] * dim
    tokens = (text or "").lower().split()
    for tok in tokens:
        h = hashlib.sha256(tok.encode()).digest()
        for i in range(dim):
            vec[i] += ((h[i % len(h)] / 255.0) - 0.5) / max(len(tokens), 1)
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]
