from __future__ import annotations

import os
from functools import lru_cache

import numpy as np

from .offline import enforce_hf_offline

DEFAULT_MODEL = os.environ.get(
    "SKILL_RAG_MODEL",
    # multilingual-e5-base: matched BGE-M3 on native English/Korean queries
    # while using materially less memory and query latency in Docker tests.
    "intfloat/multilingual-e5-base",
)
LOCAL_FILES_ONLY = os.environ.get("SKILL_RAG_LOCAL_FILES_ONLY", "1").lower() not in {
    "0",
    "false",
    "no",
}
# Hard cap on input length. Some multilingual models ship with a large default
# max sequence length; a long skill body can make the O(seq^2) attention buffer
# explode. 512 tokens covers name+description+the body's leading trigger text,
# which is what carries the retrieval signal anyway.
MAX_SEQ_LENGTH = int(os.environ.get("SKILL_RAG_MAX_SEQ_LENGTH", "512"))


@lru_cache(maxsize=4)
def _load_model(name: str):
    enforce_hf_offline(LOCAL_FILES_ONLY)
    # Imported lazily so importing this module is cheap (helps tests).
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(name, local_files_only=LOCAL_FILES_ONLY)
    # Guard against models whose default max_seq_length is very large.
    if model.max_seq_length is None or model.max_seq_length > MAX_SEQ_LENGTH:
        model.max_seq_length = MAX_SEQ_LENGTH
    return model


def model_dim(name: str = DEFAULT_MODEL) -> int:
    return int(_load_model(name).get_embedding_dimension())


def encode(texts: list[str], name: str = DEFAULT_MODEL) -> np.ndarray:
    """Encode a batch of texts. Always L2-normalized for cosine search."""
    if not texts:
        return np.zeros((0, model_dim(name)), dtype=np.float32)
    model = _load_model(name)
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


def encode_one(text: str, name: str = DEFAULT_MODEL) -> np.ndarray:
    return encode([text], name=name)[0]
