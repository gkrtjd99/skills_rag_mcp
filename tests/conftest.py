"""Shared, deterministic test doubles for the local embedding boundary.

Unit tests exercise indexing and retrieval semantics, not production-model quality.  A
small in-memory encoder keeps those tests runnable on a clean offline checkout;
the production loader remains covered separately by ``test_offline.py``.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
import pytest


class _DeterministicEmbeddingModel:
    max_seq_length = 512
    _DIM = 32

    def get_embedding_dimension(self) -> int:
        return self._DIM

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
        show_progress_bar: bool,
    ) -> np.ndarray:
        vectors = np.zeros((len(texts), self._DIM), dtype=np.float32)
        for row, text in enumerate(texts):
            # Token hashing makes repeated lexical terms share dimensions while
            # retaining a deterministic non-zero vector for arbitrary text.
            tokens = re.findall(r"[\w가-힣]+", text.lower()) or [text]
            for token in tokens:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vectors[row, int.from_bytes(digest[:4], "big") % self._DIM] += 1.0
            norm = np.linalg.norm(vectors[row])
            if norm:
                vectors[row] /= norm
        return vectors


@pytest.fixture(autouse=True)
def fake_embedding_model(monkeypatch):
    """Keep ordinary tests offline and hermetic without changing production."""
    from skill_rag import embed

    model = _DeterministicEmbeddingModel()
    monkeypatch.setattr(embed, "_load_model", lambda name: model)
