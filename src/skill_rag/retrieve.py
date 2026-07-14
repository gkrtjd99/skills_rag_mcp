from __future__ import annotations

from functools import lru_cache

from .corpus import (
    BM25_MIN_QUERY_COVERAGE,
    BM25_THRESHOLD,
    DENSE_CANDIDATE_MULTIPLIER,
    DENSE_ONLY_MARGIN_THRESHOLD,
    DENSE_ONLY_THRESHOLD,
    MAX_HIT_DESCRIPTION_CHARS,
    MAX_SEARCH_K,
    MIN_DENSE_CANDIDATES,
    MIN_SEARCH_K,
    RRF_K,
    SCORE_THRESHOLD,
)
from .embed import DEFAULT_MODEL, encode_one
from .index import list_indexed as _list_indexed
from .index import search as _index_search
from .normalize import expand_for_retrieval, normalize_for_dense
from .sparse import BM25, tokenize

_NO_MATCH = "No skill matched this query. Proceed without using a skill."
_SKIP = (
    "Query looks like a reply inside an interactive flow, not a new task. "
    "Skipped retrieval. Do not search again until the task or topic changes."
)

# Trimmed queries that carry no task signal: answers to the assistant's own
# question inside a sustained interactive flow (interview/wizard/Q&A coaching),
# not a request that could need a new skill. Matched exactly (case- and
# trailing-punctuation-insensitive) so a real query that merely *contains* one
# of these words is never skipped.
_CONVERSATIONAL = frozenset(
    {
        # Korean affirmations / negations / acknowledgements
        "네", "넵", "예", "응", "아니", "아니요", "아니오", "맞아", "맞아요",
        "좋아", "좋아요", "그래", "그래요", "오케이", "확인", "수정", "패스",
        "다음", "계속", "모르겠어요", "잘 모르겠어요", "모르겠음",
        # English
        "yes", "y", "no", "n", "ok", "okay", "yep", "yeah", "nope", "sure",
        "pass", "skip", "next", "continue", "idk", "revise", "done",
    }
)


def is_conversational(query: str) -> bool:
    """True when ``query`` is a bare reply inside an interactive flow rather than
    a task that could need a skill.

    Conservative by design — only the clearest cases skip retrieval:

    - a single alphabetic character (a multiple-choice answer: A/B/C/D),
    - an all-digit string (a numbered choice or progress answer), or
    - an exact match of the curated ko/en affirmation/ack set, ignoring case and
      trailing sentence punctuation.

    Empty queries return ``False`` here; they stay on the existing ``no_match``
    path in :func:`search`. Non-string input also returns ``False`` so the
    caller falls through to its normal validation rather than raising.
    """
    if not isinstance(query, str):
        return False
    q = query.strip()
    if not q:
        return False
    low = q.lower().rstrip(".!?…。 ").strip()
    if not low:
        return False
    if len(low) == 1 and low.isascii() and low.isalpha():
        return True
    if low.isdigit():
        return True
    return low in _CONVERSATIONAL


def skip_response() -> dict:
    """Terminal ``skip`` response for a conversational query."""
    return {"status": "skip", "hits": [], "message": _SKIP}


@lru_cache(maxsize=4)
def _bm25_for_snapshot(snapshot: tuple[tuple[str, str, str], ...]) -> BM25:
    """Build BM25 once per indexed-text snapshot, not once per query."""
    return BM25([tokenize(text) for _, _, text in snapshot])


def _compact_description(description: str) -> str:
    if MAX_HIT_DESCRIPTION_CHARS <= 0 or len(description) <= MAX_HIT_DESCRIPTION_CHARS:
        return description
    # Keep the result a valid, useful metadata string while bounding MCP
    # response tokens. The full description remains in the local index/body.
    limit = max(1, MAX_HIT_DESCRIPTION_CHARS - 1)
    return description[:limit].rstrip() + "…"


def search(
    query: str, k: int = 5, model_name: str = DEFAULT_MODEL, agent: str | None = None
) -> dict:
    """Hybrid search over the skill corpus: dense cosine + BM25, fused by RRF.

    A candidate is kept if its dense cosine clears ``SCORE_THRESHOLD`` and has
    meaningful lexical evidence (or clears ``DENSE_ONLY_THRESHOLD``), OR if
    its BM25 score (normalized by the top BM25 score) clears
    ``BM25_THRESHOLD`` with the required query-term coverage.
    Kept candidates are ordered by reciprocal rank fusion of the two rankings.

    ``agent`` names the calling harness. It is currently informational (each
    hit already reports its own source ``agent``); reserved for future
    filtering of skills the caller already loads natively.

    status:
      - "ok": at least one candidate passes either threshold
      - "no_match": empty corpus, or nothing passes
    """
    if isinstance(k, bool) or not isinstance(k, int) or not MIN_SEARCH_K <= k <= MAX_SEARCH_K:
        raise ValueError(f"k must be an integer between {MIN_SEARCH_K} and {MAX_SEARCH_K}")
    query = query.strip()
    if not query:
        return {"status": "no_match", "hits": [], "message": "Empty query. Proceed without using a skill."}

    rows = _list_indexed()
    if not rows:
        return {"status": "no_match", "hits": [], "message": _NO_MATCH}

    # --- dense: cosine over a shortlist ---
    # Same Hangul/Latin spacing the indexed text got, so both sides encode alike.
    retrieval_query = expand_for_retrieval(normalize_for_dense(query))
    vec = encode_one(retrieval_query, name=model_name)
    dense_limit = min(
        len(rows), max(k * DENSE_CANDIDATE_MULTIPLIER, MIN_DENSE_CANDIDATES)
    )
    dense = _index_search(vec, k=dense_limit, model_name=model_name)
    cosine = {h.name: h.score for h in dense}
    dense_rank = {h.name: i for i, h in enumerate(dense)}
    dense_margin = (
        dense[0].score - dense[1].score if len(dense) > 1 else dense[0].score
    ) if dense else 0.0
    description = {h.name: h.description for h in dense}
    agent_by_name = {r["name"]: r.get("agent", "unknown") for r in rows}
    for r in rows:  # fall back to indexed metadata for anything dense dropped
        description.setdefault(r["name"], r["description"])

    # --- sparse: BM25 over the full indexed text ---
    names = [r["name"] for r in rows]
    snapshot = tuple((r["path"], r["name"], r["text"]) for r in rows)
    bm25 = _bm25_for_snapshot(snapshot)
    query_tokens = tokenize(retrieval_query)
    meaningful_query_tokens = set(bm25.meaningful_query_tokens(query_tokens))
    raw_bm25 = bm25.scores(query_tokens)
    matched_terms = bm25.matched_term_counts(query_tokens)
    bm25_by_name = dict(zip(names, raw_bm25))
    top_bm25 = max(raw_bm25) if raw_bm25 else 0.0
    norm_bm25 = {
        n: (s / top_bm25 if top_bm25 > 0 else 0.0) for n, s in bm25_by_name.items()
    }
    sparse_order = sorted(
        (n for n in names if bm25_by_name[n] > 0),
        key=lambda n: bm25_by_name[n],
        reverse=True,
    )
    sparse_rank = {n: i for i, n in enumerate(sparse_order)}

    # --- keep candidates that pass either signal, order by RRF ---
    lexical_pass = {
        n: (
            norm_bm25.get(n, 0.0) >= BM25_THRESHOLD
            and (
                len(meaningful_query_tokens) <= 1
                or (
                    matched_terms[i] / len(meaningful_query_tokens)
                    >= BM25_MIN_QUERY_COVERAGE
                )
            )
        )
        for i, n in enumerate(names)
    }
    dense_pass = {
        n: (
            cosine.get(n, 0.0) >= SCORE_THRESHOLD
            and (
                # An explicit zero threshold is the evaluator/debug mode:
                # preserve its request to keep every dense candidate.
                SCORE_THRESHOLD <= 0.0
                or cosine.get(n, 0.0) >= DENSE_ONLY_THRESHOLD
                or (
                    dense_rank.get(n) == 0
                    and dense_margin >= DENSE_ONLY_MARGIN_THRESHOLD
                )
                or matched_terms[i] > 0
            )
        )
        for i, n in enumerate(names)
    }
    kept = [n for n in names if dense_pass[n] or lexical_pass[n]]
    if not kept:
        return {"status": "no_match", "hits": [], "message": _NO_MATCH}

    def rrf(n: str) -> float:
        score = 0.0
        if n in dense_rank:
            score += 1.0 / (RRF_K + dense_rank[n])
        if n in sparse_rank:
            score += 1.0 / (RRF_K + sparse_rank[n])
        return score

    # The public score must describe the ordering users receive. Previously it
    # exposed the dense cosine while ordering used RRF, so a lower-ranked hit
    # could display a higher score than the hit above it. Normalize the fused
    # score against the best hit for this query; this adds no response fields
    # and keeps the score useful without pretending it is comparable across
    # unrelated queries.
    hybrid_scores = {n: rrf(n) for n in kept}
    kept.sort(key=lambda n: hybrid_scores[n], reverse=True)
    top_hybrid_score = hybrid_scores[kept[0]]
    # A zero threshold is useful in tests/debugging and can intentionally keep
    # a candidate with no ranked signal. Do not let that diagnostic mode divide
    # by zero; production candidates have a positive dense or sparse rank.
    score_scale = top_hybrid_score if top_hybrid_score > 0.0 else 1.0
    hits = [
        {
            "name": n,
            "description": _compact_description(description.get(n, "")),
            "score": round(hybrid_scores[n] / score_scale, 4),
            "agent": agent_by_name.get(n, "unknown"),
        }
        for n in kept[:k]
    ]
    return {"status": "ok", "hits": hits}
