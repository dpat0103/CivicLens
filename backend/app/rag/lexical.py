"""
Lexical retrieval (BM25) to sit alongside dense vector retrieval.

Why both
--------
Dense vectors are good at meaning and bad at exact tokens. A question about
"Montclair" needs the chunk that literally says Montclair, and an embedding
that has smoothed "Montclair" toward "Bloomfield" will happily return the
wrong town. BM25 is the opposite: excellent on exact terms, blind to
paraphrase.

Running both and fusing the rankings covers each one's weakness, and it is
what production retrieval systems generally do rather than picking a side.
It also means the offline path stops depending entirely on a hashing
embedder that cannot do semantics at all.

BM25 is computed in-process over the chunk table. The corpus is a few
thousand short documents, so building the index costs milliseconds and
avoids adding a search service to the stack.
"""
from __future__ import annotations

import math
import re
from collections import Counter

# Standard BM25 parameters. k1 controls how fast term frequency saturates,
# b controls how much document length normalisation is applied.
K1 = 1.5
B = 0.75

_TOKEN = re.compile(r"[a-z0-9]+")

# Words that appear in nearly every fact card and carry no signal for
# telling one municipality or category apart.
_STOPWORDS = frozenset("""
a an and are as at be been by for from had has have in into is it its of on
or that the this to was were what when where which who will with
county new jersey nj municipality
""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOPWORDS and len(t) > 1]


class BM25Index:
    """Okapi BM25 over a fixed set of documents."""

    def __init__(self, documents: list[str]):
        self.doc_tokens = [tokenize(d) for d in documents]
        self.doc_lengths = [len(t) for t in self.doc_tokens]
        self.doc_count = len(documents)
        self.avg_length = (
            sum(self.doc_lengths) / self.doc_count if self.doc_count else 0.0
        )

        self.term_freqs: list[Counter] = [Counter(t) for t in self.doc_tokens]

        document_freq: Counter = Counter()
        for tokens in self.doc_tokens:
            document_freq.update(set(tokens))

        # Standard BM25 idf with the +1 smoothing that keeps very common
        # terms from going negative.
        self.idf = {
            term: math.log(1 + (self.doc_count - freq + 0.5) / (freq + 0.5))
            for term, freq in document_freq.items()
        }

    def scores(self, query: str) -> list[float]:
        query_terms = tokenize(query)
        out = [0.0] * self.doc_count
        if not query_terms or not self.doc_count:
            return out

        for index in range(self.doc_count):
            length = self.doc_lengths[index]
            freqs = self.term_freqs[index]
            score = 0.0
            for term in query_terms:
                tf = freqs.get(term, 0)
                if tf == 0:
                    continue
                idf = self.idf.get(term, 0.0)
                denominator = tf + K1 * (1 - B + B * length / (self.avg_length or 1))
                score += idf * (tf * (K1 + 1)) / denominator
            out[index] = score
        return out


def reciprocal_rank_fusion(
    rankings: list[list[int]], k: int = 60
) -> dict[int, float]:
    """Combine several rankings of the same documents into one.

    RRF scores a document by the sum of 1/(k + rank) across the rankings it
    appears in. It deliberately uses rank rather than raw score, which is
    what makes it safe to fuse BM25 (unbounded, corpus-dependent) with
    cosine similarity (bounded, roughly 0 to 1). Normalising two scales that
    different into a weighted sum requires tuning that would not survive
    swapping the embedding provider; ranks need no tuning at all.

    k=60 is the value from the original RRF paper and dampens the influence
    of the very top ranks so one retriever cannot dominate.
    """
    fused: dict[int, float] = {}
    for ranking in rankings:
        for rank, doc_index in enumerate(ranking):
            fused[doc_index] = fused.get(doc_index, 0.0) + 1.0 / (k + rank + 1)
    return fused
