"""Text similarity for "find similar failures" (SPEC.md §8 page 1).

Two backends behind one function:

* embeddings from a judge (``judge.embed``) when an embedding model is configured;
* a dependency-free fallback: hashed bag-of-words with sublinear TF and cosine
  similarity. Coarse, but deterministic and good enough to surface traces with the
  same failure shape (same tool, same refund question, same leaked canary).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence

_TOKEN = re.compile(r"[a-z0-9]{2,}")
DIM = 4096


def hashed_vector(text: str, dim: int = DIM) -> list[float]:
    vec = [0.0] * dim
    for tok in _TOKEN.findall(text.lower()):
        idx = int(hashlib.blake2b(tok.encode(), digest_size=4).hexdigest(), 16) % dim
        vec[idx] += 1.0
    # sublinear tf + l2 normalise
    vec = [1 + math.log(v) if v > 0 else 0.0 for v in vec]
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rank_similar(
    query: str, candidates: Sequence[tuple[str, str]], *, limit: int = 5
) -> list[tuple[str, float]]:
    """Return ``[(id, score)]`` for the most similar candidate texts (hashed BoW backend)."""
    q = hashed_vector(query)
    scored = [(cid, cosine(q, hashed_vector(text))) for cid, text in candidates if text]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
