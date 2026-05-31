"""Minimal in-memory BM25 for lexical (keyword) retrieval.

The dense embedding model is cross-lingual but weak on short text and exact
tokens (skill names, "vercel", "EXPLAIN ANALYZE"). BM25 over the full skill
text complements it. With ~100 skills, building the index per query is cheap,
so there is no persistence and no extra dependency.
"""

from __future__ import annotations

import math
import re
from collections import Counter

_WORD = re.compile(r"\w+", re.UNICODE)
# Precomposed Hangul syllables. Particles glue to stems here (vercel에, 코드리뷰),
# so a whitespace tokenizer never recovers the stem. We split each \w run into
# Hangul / non-Hangul segments and char-bigram the Hangul so partial overlap
# ('코드리뷰' vs '코드 리뷰') still matches under BM25.
_SEGMENT = re.compile(r"[가-힣]+|[^가-힣]+")
_IS_HANGUL = re.compile(r"[가-힣]")


def _bigrams(run: str) -> list[str]:
    if len(run) <= 2:
        return [run]
    return [run[i : i + 2] for i in range(len(run) - 1)]


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for match in _WORD.finditer(text.lower()):
        for seg in _SEGMENT.findall(match.group()):
            if _IS_HANGUL.match(seg):
                out.extend(_bigrams(seg))
            else:
                out.append(seg)
    return out


class BM25:
    """Okapi BM25 over a fixed list of tokenized documents."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.n = len(docs)
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs]
        df: Counter[str] = Counter()
        for d in docs:
            for term in set(d):
                df[term] += 1
        # Probabilistic idf with +1 so common terms stay non-negative.
        self.idf = {
            term: math.log(1 + (self.n - freq + 0.5) / (freq + 0.5))
            for term, freq in df.items()
        }

    def scores(self, query_tokens: list[str]) -> list[float]:
        out = [0.0] * self.n
        if not self.n or self.avgdl == 0.0:
            return out
        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i in range(self.n):
                freq = self.tf[i].get(term, 0)
                if not freq:
                    continue
                denom = freq + self.k1 * (
                    1 - self.b + self.b * self.doc_len[i] / self.avgdl
                )
                out[i] += idf * (freq * (self.k1 + 1)) / denom
        return out
