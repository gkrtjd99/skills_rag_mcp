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
# Hard cap on input length. Skill names, descriptions, and the leading trigger
# section carry the retrieval signal; indexing all 512 tokens made a 1,925-skill
# first MCP search take about 51 seconds. Description-only passages fit
# comfortably in 64 tokens for the measured corpus and retain 1.0 recall on
# the bilingual fixture.
MAX_SEQ_LENGTH = int(os.environ.get("SKILL_RAG_MAX_SEQ_LENGTH", "64"))


def _uses_e5_prompt(name: str) -> bool:
    """Return whether ``name`` is an E5-family model.

    E5 models are trained with different query and passage prefixes. Keeping
    this at the embedding boundary lets callers use native text while still
    getting the model's intended cross-lingual behavior. Other models (for
    example BGE-M3 overrides) remain unmodified.
    """
    return "e5" in name.lower()


def _prepare_text(text: str, name: str, mode: str) -> str:
    if mode not in {"query", "passage"}:
        raise ValueError("embedding mode must be 'query' or 'passage'")
    if not _uses_e5_prompt(name):
        return text
    return f"{mode}: {text}"


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


def encode(
    texts: list[str], name: str = DEFAULT_MODEL, *, mode: str = "passage"
) -> np.ndarray:
    """Encode passages or queries. Always L2-normalized for cosine search."""
    if not texts:
        return np.zeros((0, model_dim(name)), dtype=np.float32)
    model = _load_model(name)
    vectors = model.encode(
        [_prepare_text(text, name, mode) for text in texts],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return vectors.astype(np.float32)


def encode_one(
    text: str, name: str = DEFAULT_MODEL, *, mode: str = "query"
) -> np.ndarray:
    return encode([text], name=name, mode=mode)[0]
