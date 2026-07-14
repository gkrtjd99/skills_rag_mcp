from __future__ import annotations

import os
from pathlib import Path

CORPUS_PATH = Path(os.environ.get("SKILL_RAG_CORPUS_PATH", "~/.skills")).expanduser()
BOOTSTRAP_SKILL_NAME = "using-skill-rag"
# E5 scores are deliberately calibrated against the public positive and
# negative fixtures. The old 0.45 bar admitted semantically related but
# unrelated requests (for example weather questions on a five-skill corpus).
# Exact names and code terms still have the BM25 rescue path below.
SCORE_THRESHOLD = float(os.environ.get("SKILL_RAG_SCORE_THRESHOLD", "0.78"))
# A candidate also passes if its BM25 score normalized by the top BM25 score
# clears this bar — the lexical rescue path for exact keywords the dense
# cross-lingual vector underweights.
BM25_THRESHOLD = float(os.environ.get("SKILL_RAG_BM25_THRESHOLD", "0.30"))
# A lexical rescue must cover at least half of the meaningful query terms;
# otherwise a generic word such as "write" can make an unrelated skill pass.
BM25_MIN_QUERY_COVERAGE = float(
    os.environ.get("SKILL_RAG_BM25_MIN_QUERY_COVERAGE", "0.50")
)
# E5 cosine scores have a high baseline on arbitrary text. A dense-only hit
# therefore needs either lexical evidence or a materially higher confidence
# score; this blocks nonsense queries that otherwise look semantically close.
DENSE_ONLY_THRESHOLD = float(
    os.environ.get("SKILL_RAG_DENSE_ONLY_THRESHOLD", "0.86")
)
# A strong top-vs-runner-up separation is another valid dense-only signal,
# especially for a small corpus where absolute cosine scores are lower.
DENSE_ONLY_MARGIN_THRESHOLD = float(
    os.environ.get("SKILL_RAG_DENSE_ONLY_MARGIN_THRESHOLD", "0.05")
)
# Reciprocal-rank-fusion damping constant.
RRF_K = int(os.environ.get("SKILL_RAG_RRF_K", "60"))
SYNC_TTL_SECONDS = float(os.environ.get("SKILL_RAG_SYNC_TTL", "30"))
MIN_SEARCH_K = 1
MAX_SEARCH_K = 50
# Dense ranking is only needed for the candidates that can be returned or
# fused. BM25 still scans the complete corpus, so an exact lexical match is
# not lost just because it is outside this dense shortlist.
DENSE_CANDIDATE_MULTIPLIER = int(
    os.environ.get("SKILL_RAG_DENSE_CANDIDATE_MULTIPLIER", "4")
)
MIN_DENSE_CANDIDATES = int(os.environ.get("SKILL_RAG_MIN_DENSE_CANDIDATES", "20"))
# Search results are metadata-only. Cap descriptions so a five-hit MCP result
# does not spend the agent's context budget repeating long frontmatter.
MAX_HIT_DESCRIPTION_CHARS = int(
    os.environ.get("SKILL_RAG_MAX_HIT_DESCRIPTION_CHARS", "280")
)
# Dense retrieval needs the skill's trigger vocabulary, not its entire
# instruction body. BM25 keeps the full body in `text` for exact rescue.
# Descriptions are the canonical discovery surface; a short body prefix can be
# opted into for corpora with sparse descriptions.
DENSE_BODY_CHARS = int(os.environ.get("SKILL_RAG_DENSE_BODY_CHARS", "0"))
