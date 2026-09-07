"""
Embedding providers.

Design note
-----------
Render's free tier caps at 512MB of RAM, which rules out running a local
sentence-transformers model (torch alone blows the ceiling). So production
uses a hosted embeddings API, and everything sits behind a small protocol
so the provider is a config change rather than a code change.

`HashingEmbedder` is a real, deterministic, dependency-free embedder used
for tests and CI. It lets the whole retrieval pipeline be exercised without
network access or API keys. It is a character n-gram hashing vectorizer,
so it captures lexical overlap but not semantics -- good enough to assert
that filtering, ranking and citation plumbing behave, not good enough for
production relevance.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

import numpy as np

EMBED_DIM = 384


class EmbeddingProvider(Protocol):
    dim: int

    def embed(self, texts: list[str]) -> np.ndarray:
        """Return an (n, dim) L2-normalized float32 array."""
        ...


def _l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class HashingEmbedder:
    """Deterministic offline embedder. Same input always yields the same
    vector, in this process or any other, which is what makes the retrieval
    eval suite reproducible."""

    def __init__(self, dim: int = EMBED_DIM):
        self.dim = dim

    @staticmethod
    def _tokens(text: str) -> list[str]:
        words = re.findall(r"[a-z0-9]+", text.lower())
        grams = list(words)
        for w in words:
            padded = f" {w} "
            for i in range(len(padded) - 2):
                grams.append(padded[i:i + 3])
        for i in range(len(words) - 1):
            grams.append(f"{words[i]}_{words[i + 1]}")
        return grams

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            counts: dict[int, float] = {}
            for tok in self._tokens(text):
                digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "big") % self.dim
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                counts[idx] = counts.get(idx, 0.0) + sign
            for idx, val in counts.items():
                # Signed hashing means two tokens landing on the same bucket
                # with opposite signs can cancel to exactly zero. That is the
                # intended collision behaviour, but log(0) is a domain error,
                # so drop the bucket rather than scaling it.
                if val == 0:
                    continue
                # sublinear scaling, same rationale as tf-idf's log term
                out[row, idx] = math.copysign(1.0 + math.log(abs(val)), val)
        return _l2_normalize(out)


class _HttpEmbedder:
    """Shared plumbing for hosted providers."""

    endpoint: str = ""
    model: str = ""
    dim: int = 0

    def __init__(self, api_key: str, model: str | None = None):
        if not api_key:
            raise ValueError(f"{type(self).__name__} requires an API key")
        self.api_key = api_key
        if model:
            self.model = model

    def _payload(self, texts: list[str]) -> dict:
        raise NotImplementedError

    def _headers(self) -> dict:
        raise NotImplementedError

    def _parse(self, data: dict) -> list[list[float]]:
        raise NotImplementedError

    def embed(self, texts: list[str]) -> np.ndarray:
        import requests

        vectors: list[list[float]] = []
        # Hosted APIs cap batch size, and Render's free instance has a short
        # request timeout, so chunk rather than sending 3k cards at once.
        for start in range(0, len(texts), 96):
            batch = texts[start:start + 96]
            resp = requests.post(
                self.endpoint,
                headers=self._headers(),
                json=self._payload(batch),
                timeout=60,
            )
            resp.raise_for_status()
            vectors.extend(self._parse(resp.json()))
        return _l2_normalize(np.array(vectors, dtype=np.float32))


class VoyageEmbedder(_HttpEmbedder):
    endpoint = "https://api.voyageai.com/v1/embeddings"
    model = "voyage-3-lite"
    dim = 512

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, texts: list[str]) -> dict:
        return {"model": self.model, "input": texts, "input_type": "document"}

    def _parse(self, data: dict) -> list[list[float]]:
        return [item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])]


class OpenAIEmbedder(_HttpEmbedder):
    endpoint = "https://api.openai.com/v1/embeddings"
    model = "text-embedding-3-small"
    dim = 1536

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, texts: list[str]) -> dict:
        return {"model": self.model, "input": texts}

    def _parse(self, data: dict) -> list[list[float]]:
        return [item["embedding"] for item in sorted(data["data"], key=lambda d: d["index"])]


def get_embedder() -> EmbeddingProvider:
    """Resolve the provider from EMBEDDING_PROVIDER. Defaults to the offline
    hashing embedder so the app boots with zero configuration."""
    provider = os.getenv("EMBEDDING_PROVIDER", "hashing").lower()
    if provider == "voyage":
        return VoyageEmbedder(os.getenv("VOYAGE_API_KEY", ""))
    if provider == "openai":
        return OpenAIEmbedder(os.getenv("OPENAI_API_KEY", ""))
    if provider == "hashing":
        return HashingEmbedder()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER '{provider}'")
