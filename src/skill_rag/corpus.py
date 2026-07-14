from __future__ import annotations

import os
from pathlib import Path

CORPUS_PATH = Path(os.environ.get("SKILL_RAG_CORPUS_PATH", "~/.skills")).expanduser()
BOOTSTRAP_SKILL_NAME = "using-skill-rag"
# Retained at 0.45 after switching the default to multilingual-e5-base; the
# native English/Korean dynamic benchmark passed at this threshold.
SCORE_THRESHOLD = float(os.environ.get("SKILL_RAG_SCORE_THRESHOLD", "0.45"))
# A candidate also passes if its BM25 score normalized by the top BM25 score
# clears this bar — the lexical rescue path for exact keywords the dense
# cross-lingual vector underweights.
BM25_THRESHOLD = float(os.environ.get("SKILL_RAG_BM25_THRESHOLD", "0.30"))
# Reciprocal-rank-fusion damping constant.
RRF_K = int(os.environ.get("SKILL_RAG_RRF_K", "60"))
SYNC_TTL_SECONDS = float(os.environ.get("SKILL_RAG_SYNC_TTL", "30"))
MIN_SEARCH_K = 1
MAX_SEARCH_K = 50
