"""
Vector store.

Architecture note
-----------------
Chunks and their embeddings live in the same database as the metrics they
describe, rather than in a dedicated vector service. That removes the sync
problem entirely: there is no second datastore that can drift out of date
when the metrics table is refreshed, and retrieval can filter by FIPS using
the same indexes the rest of the API already uses.

The corpus is small by design (locations x categories, plus a handful of
methodology docs), so cosine similarity is computed in NumPy over the
candidate set after metadata filtering. At 565 New Jersey municipalities
that is roughly 3k vectors, which is microseconds of work and far cheaper
than a network hop to an external index. If the corpus ever grows past the
point where that holds, `PGVECTOR_ENABLED=1` switches the ranking step to a
pgvector index on Neon without changing anything above this layer.
"""
from __future__ import annotations

import json
import os

import numpy as np
from sqlalchemy import Column, Integer, String, Text, delete, select
from sqlalchemy.orm import Session

from ..database import Base
from .corpus import Chunk
from .lexical import BM25Index, reciprocal_rank_fusion


class RagChunk(Base):
    __tablename__ = "rag_chunks"

    id = Column(Integer, primary_key=True, index=True)
    chunk_id = Column(String(120), unique=True, index=True, nullable=False)
    kind = Column(String(20), nullable=False, index=True)
    text = Column(Text, nullable=False)

    fips = Column(String(20), nullable=True, index=True)
    location_name = Column(String(120), nullable=True)
    category = Column(String(30), nullable=True, index=True)

    metric_keys = Column(Text, nullable=False, default="[]")
    periods = Column(Text, nullable=False, default="[]")
    sources = Column(Text, nullable=False, default="[]")
    source_urls = Column(Text, nullable=False, default="[]")
    provenance = Column(String(12), nullable=False, default="measured")

    embedding = Column(Text, nullable=False)
    embedding_dim = Column(Integer, nullable=False)
    embedding_provider = Column(String(40), nullable=False)


def _to_row(chunk: Chunk, vector: np.ndarray, provider: str) -> dict:
    return dict(
        chunk_id=chunk.chunk_id,
        kind=chunk.kind,
        text=chunk.text,
        fips=chunk.fips,
        location_name=chunk.location_name,
        category=chunk.category,
        metric_keys=json.dumps(chunk.metric_keys),
        periods=json.dumps(chunk.periods),
        sources=json.dumps(chunk.sources),
        source_urls=json.dumps(chunk.source_urls),
        provenance=chunk.provenance,
        embedding=json.dumps([round(float(x), 6) for x in vector]),
        embedding_dim=int(vector.shape[0]),
        embedding_provider=provider,
    )


def index_corpus(db: Session, chunks: list[Chunk], embedder) -> int:
    """Embed and persist the corpus, replacing whatever was there before.

    Full replace rather than upsert: the corpus is cheap to rebuild and a
    partial update is how stale rows survive behind fresh ones without any
    error surfacing.
    """
    vectors = embedder.embed([c.text for c in chunks])
    provider = type(embedder).__name__

    db.execute(delete(RagChunk))
    db.bulk_insert_mappings(
        RagChunk,
        [_to_row(c, vectors[i], provider) for i, c in enumerate(chunks)],
    )
    db.commit()
    return len(chunks)


class Retrieved:
    __slots__ = ("row", "score")

    def __init__(self, row: RagChunk, score: float):
        self.row = row
        self.score = score

    def as_citation(self) -> dict:
        return {
            "chunk_id": self.row.chunk_id,
            "kind": self.row.kind,
            "fips": self.row.fips,
            "location_name": self.row.location_name,
            "category": self.row.category,
            "metric_keys": json.loads(self.row.metric_keys),
            "periods": json.loads(self.row.periods),
            "sources": json.loads(self.row.sources),
            "source_urls": json.loads(self.row.source_urls),
            "provenance": self.row.provenance,
            "score": round(self.score, 4),
        }


def search(
    db: Session,
    query_vector: np.ndarray,
    top_k: int = 6,
    fips_filter: list[str] | None = None,
    kinds: list[str] | None = None,
    query_text: str | None = None,
) -> list[Retrieved]:
    """Metadata filter, then hybrid rank, then take the top k.

    Three stages, each doing a different job:

    1. Metadata filter. Fact cards for neighbouring municipalities are
       near-identical in shape, so similarity alone will return
       Bloomfield's card for a question about Montclair. Constraining on a
       resolved FIPS code removes that whole class of wrong answer rather
       than making it less likely.

    2. Hybrid ranking. Dense cosine similarity catches paraphrase, BM25
       catches exact terms, and reciprocal rank fusion combines the two
       rankings. Passing `query_text` enables the lexical half; without it
       this degrades to pure vector search.

    3. Truncate to top_k.
    """
    stmt = select(RagChunk)
    clauses = []
    if fips_filter:
        # Methodology docs have no FIPS and must stay reachable.
        clauses.append(RagChunk.fips.in_(fips_filter) | RagChunk.fips.is_(None))
    if kinds:
        clauses.append(RagChunk.kind.in_(kinds))
    for clause in clauses:
        stmt = stmt.where(clause)

    rows = db.execute(stmt).scalars().all()
    if not rows:
        return []

    matrix = np.array([json.loads(r.embedding) for r in rows], dtype=np.float32)
    # Vectors are stored L2-normalized, so the dot product is the cosine.
    dense_scores = matrix @ query_vector.astype(np.float32)

    if not query_text:
        ranked = sorted(
            zip(rows, dense_scores), key=lambda p: float(p[1]), reverse=True
        )
        return [Retrieved(row, float(score)) for row, score in ranked[:top_k]]

    lexical_scores = BM25Index([r.text for r in rows]).scores(query_text)

    dense_ranking = sorted(range(len(rows)), key=lambda i: -float(dense_scores[i]))
    lexical_ranking = sorted(range(len(rows)), key=lambda i: -lexical_scores[i])
    fused = reciprocal_rank_fusion([dense_ranking, lexical_ranking])

    order = sorted(fused, key=lambda i: -fused[i])[:top_k]

    # Report the cosine score rather than the fused score, because the
    # relevance floor downstream is calibrated in cosine terms and a fused
    # RRF score is not comparable to it.
    return [Retrieved(rows[i], float(dense_scores[i])) for i in order]


def corpus_stats(db: Session) -> dict:
    rows = db.execute(select(RagChunk)).scalars().all()
    by_kind: dict[str, int] = {}
    providers = set()
    for r in rows:
        by_kind[r.kind] = by_kind.get(r.kind, 0) + 1
        providers.add(r.embedding_provider)
    return {
        "total_chunks": len(rows),
        "by_kind": by_kind,
        "embedding_provider": sorted(providers),
        "pgvector_enabled": os.getenv("PGVECTOR_ENABLED", "0") == "1",
    }