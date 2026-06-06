from __future__ import annotations

from .corpus import BM25_THRESHOLD, RRF_K, SCORE_THRESHOLD
from .embed import DEFAULT_MODEL, encode_one
from .index import list_indexed as _list_indexed
from .index import search as _index_search
from .normalize import normalize_for_dense
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
    if len(low) == 1 and low.isalpha():
        return True
    if low.isdigit():
        return True
    return low in _CONVERSATIONAL


def skip_response() -> dict:
    """Terminal ``skip`` response for a conversational query."""
    return {"status": "skip", "hits": [], "message": _SKIP}


def search(
    query: str, k: int = 5, model_name: str = DEFAULT_MODEL, agent: str | None = None
) -> dict:
    """Hybrid search over the skill corpus: dense cosine + BM25, fused by RRF.

    A candidate is kept if its dense cosine clears ``SCORE_THRESHOLD`` OR its
    BM25 score (normalized by the top BM25 score) clears ``BM25_THRESHOLD``.
    Kept candidates are ordered by reciprocal rank fusion of the two rankings.

    ``agent`` names the calling harness. It is currently informational (each
    hit already reports its own source ``agent``); reserved for future
    filtering of skills the caller already loads natively.

    status:
      - "ok": at least one candidate passes either threshold
      - "no_match": empty corpus, or nothing passes
    """
    query = query.strip()
    if not query:
        return {"status": "no_match", "hits": [], "message": "Empty query. Proceed without using a skill."}

    rows = _list_indexed()
    if not rows:
        return {"status": "no_match", "hits": [], "message": _NO_MATCH}

    # --- dense: cosine over the whole corpus so every candidate has a score ---
    # Same Hangul/Latin spacing the indexed text got, so both sides encode alike.
    vec = encode_one(normalize_for_dense(query), name=model_name)
    dense = _index_search(vec, k=len(rows))
    cosine = {h.name: h.score for h in dense}
    dense_rank = {h.name: i for i, h in enumerate(dense)}
    description = {h.name: h.description for h in dense}
    agent_by_name = {r["name"]: r.get("agent", "unknown") for r in rows}
    for r in rows:  # fall back to indexed metadata for anything dense dropped
        description.setdefault(r["name"], r["description"])

    # --- sparse: BM25 over the full indexed text ---
    names = [r["name"] for r in rows]
    bm25 = BM25([tokenize(r["text"]) for r in rows])
    raw_bm25 = bm25.scores(tokenize(query))
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
    kept = [
        n
        for n in names
        if cosine.get(n, 0.0) >= SCORE_THRESHOLD or norm_bm25.get(n, 0.0) >= BM25_THRESHOLD
    ]
    if not kept:
        return {"status": "no_match", "hits": [], "message": _NO_MATCH}

    def rrf(n: str) -> float:
        score = 0.0
        if n in dense_rank:
            score += 1.0 / (RRF_K + dense_rank[n])
        if n in sparse_rank:
            score += 1.0 / (RRF_K + sparse_rank[n])
        return score

    kept.sort(key=rrf, reverse=True)
    hits = [
        {
            "name": n,
            "description": description.get(n, ""),
            "score": round(cosine.get(n, 0.0), 4),
            "agent": agent_by_name.get(n, "unknown"),
        }
        for n in kept[:k]
    ]
    return {"status": "ok", "hits": hits}
