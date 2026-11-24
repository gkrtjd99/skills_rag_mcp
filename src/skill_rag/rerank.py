"""Opt-in second-stage fit judgment by a swappable model.

Off by default: without ``SKILL_RAG_RERANK`` every search is the local hybrid
gate in ``retrieve.py`` and nothing leaves the machine.

When enabled, the local hybrid ranking only proposes a shortlist. A judge
(``skill_rag.judges``: ``jev``, ``openai``, or your own ``module:factory``)
returns, per shortlisted skill, the probability that it fits the query. The
policy is precision first: a wrong skill costs the agent a skill body's worth
of tokens and can steer it wrong, while no skill costs only the help it would
have given. So only a skill at or above ``RERANK_THRESHOLD`` (0.9) is
returned, and by default only the single best one; its probability is the hit
``score``. The built-in judges are cloud calls: they send the query text and
the shortlisted skills' names and descriptions to the provider. Skill bodies,
paths, and the rest of the corpus are never sent.

``RERANK_SCAN_MAX`` > 0 additionally lets the judge scan the whole corpus to
build the shortlist. It finds the right skill more often but also returns more
skills that do not fit, so it is off by default.

Any failure (unknown provider, missing package or key, no API credits, timeout,
API error, malformed answer) falls back to the local gate, so enabling this can
never make search unavailable. After a failure the judge is skipped for a short
cooldown so a persistent outage does not add a failed round trip to every
search.

This module owns the policy; a judge only scores. Mirrors translate.py:
env-driven config, lazy dependency import, cached instance.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from time import monotonic as _monotonic

from . import judges, retrieve

_log = logging.getLogger(__name__)

RERANK_PROVIDER = os.environ.get("SKILL_RAG_RERANK", "").strip()
# The shortlist only has to contain the right skill; the judge decides the
# rest. Measured with Jev on the held-out 40-skill corpus
# (docs/benchmarks/2026-11-24-*): 8 candidates -> recall@1 0.925, ~2.4k input
# tokens, p50 ~275 ms; 16 candidates -> recall@1 0.988, ~4.4k input tokens,
# p50 ~555 ms. Both kept no-match accuracy at 1.000 on that author-written
# set; the scale benchmark (docs/benchmarks/2026-11-24-scale-results.md) is
# harsher and shows the shortlist, not the judge, limiting recall as the
# corpus grows. Search runs once per task, so the default favors not missing
# the skill.
RERANK_CANDIDATES = int(os.environ.get("SKILL_RAG_RERANK_CANDIDATES", "16"))
# Chosen on a dev set for precision first
# (docs/benchmarks/2026-11-24-precision-results.md). At 0.5 a skill that does
# not fit was returned for 41% of dev requests with no matching skill and 12%
# of those with one; at 0.9 for 9% and 3%, while a useful skill was returned
# for 67% of requests that had one instead of 80%.
RERANK_THRESHOLD = float(os.environ.get("SKILL_RAG_RERANK_THRESHOLD", "0.9"))
# Skills returned per search. One by default: every extra hit is another
# chance to hand the agent a skill that does not fit. 0 means up to ``k``.
RERANK_MAX_HITS = int(os.environ.get("SKILL_RAG_RERANK_MAX_HITS", "1"))
RERANK_TIMEOUT = float(os.environ.get("SKILL_RAG_RERANK_TIMEOUT", "5"))
# Empty means the provider's default model. Pin a version for stable scores.
RERANK_MODEL = os.environ.get("SKILL_RAG_RERANK_MODEL", "").strip()
# Seconds to stay on the local gate after a failed judge call. A failed call
# measured ~600 ms; without this an expired key or empty credit balance would
# add that to every search.
RERANK_COOLDOWN_SECONDS = float(os.environ.get("SKILL_RAG_RERANK_COOLDOWN", "60"))
# A judged hit no longer needs its description to be re-judged by the agent,
# only recognized, so it is returned shorter than a local-gate hit (280).
RERANK_DESCRIPTION_CHARS = int(os.environ.get("SKILL_RAG_RERANK_DESCRIPTION_CHARS", "120"))
# Largest corpus the judge scans whole to build the shortlist; 0 (default)
# turns the scan off. On the dev set a scan put the right skill in the top 16
# for 97% of queries against 74% for the local shortlist, but at every
# threshold it also returned more skills that do not fit, so it lost the
# precision-first selection. A scan costs about 51 input tokens per skill.
RERANK_SCAN_MAX = int(os.environ.get("SKILL_RAG_RERANK_SCAN_MAX", "0"))

_retry_after: float = 0.0  # monotonic deadline of the current cooldown


def enabled() -> bool:
    return judges.is_known(RERANK_PROVIDER)


@lru_cache(maxsize=4)
def _load_judge(provider: str, model: str, timeout: float) -> judges.Judge:
    return judges.load(provider, judges.JudgeConfig(model=model, timeout=timeout))


def current_judge() -> judges.Judge:
    """The configured judge, built once per (provider, model, timeout)."""
    return _load_judge(RERANK_PROVIDER, RERANK_MODEL, RERANK_TIMEOUT)


def readiness() -> str:
    """Why the next search will or will not use a judge, for ``skill-rag status``."""
    if not RERANK_PROVIDER:
        return "off"
    if not enabled():
        return f"off (unknown provider {RERANK_PROVIDER!r})"
    try:
        current = current_judge()
        reason = current.unavailable_reason()
    except Exception as exc:
        return f"{RERANK_PROVIDER} (unavailable: {type(exc).__name__}: {exc}; using local gate)"
    if reason:
        return f"{RERANK_PROVIDER} (unavailable: {reason}; using local gate)"
    destination = getattr(current, "destination", "")
    sends = f"sends query and shortlisted descriptions to {destination}" if destination else "local"
    return f"{RERANK_PROVIDER} ({sends})"


def judge(query: str, candidates: list[dict]) -> list[float]:
    """Probability that each candidate fits ``query``, aligned with ``candidates``."""
    return judges.checked(current_judge().fits(query, candidates), len(candidates))


def scan(query: str, candidates: list[dict]) -> list[float]:
    """Coarse probability for every candidate, aligned with ``candidates``."""
    current = current_judge()
    coarse = getattr(current, "scan", None)
    if coarse is None:
        # A judge without a scan method: same question, shorter descriptions.
        cut = judges.SCAN_DESCRIPTION_CHARS
        candidates = [{**c, "description": c["description"][:cut]} for c in candidates]
        coarse = current.fits
    return judges.checked(coarse(query, candidates), len(candidates))


def _shortlist(query: str, size: int, exclude: frozenset[str] = frozenset()) -> list[dict]:
    """Candidates for the fit judgment: scanned by the judge when the corpus
    is small enough, otherwise the local hybrid ranking."""
    total = retrieve.corpus_size()
    if not size < total <= RERANK_SCAN_MAX:
        return retrieve.shortlist(query, size, exclude=exclude)
    everything = retrieve.shortlist(query, total, exclude=exclude)
    if len(everything) <= size:
        return everything
    coarse = scan(query, everything)
    # Stable sort: equal probabilities keep the hybrid order.
    order = sorted(range(len(everything)), key=lambda i: coarse[i], reverse=True)
    return [everything[i] for i in order[:size]]


def search(
    query: str, k: int = 5, agent: str | None = None, exclude: frozenset[str] = frozenset()
) -> dict:
    """``retrieve.search`` contract, with a judge deciding fit when enabled."""
    local = lambda: retrieve.search(query, k=k, agent=agent, exclude=exclude)
    if not enabled():
        return local()
    global _retry_after
    if _monotonic() < _retry_after:
        return local()
    if not query.strip() or retrieve.corpus_size() == 0:
        # Empty query or corpus: keep the local path's own messages.
        return local()
    try:
        candidates = _shortlist(query, max(k, RERANK_CANDIDATES), exclude)
        if not candidates:
            return retrieve.no_match_response()
        fits = judge(query, candidates)
    except Exception as exc:
        _retry_after = _monotonic() + RERANK_COOLDOWN_SECONDS
        status = getattr(exc, "status", None) or getattr(
            getattr(exc, "response", None), "status_code", None
        )
        # Never log the query or skill text (see SECURITY.md).
        _log.warning(
            "rerank unavailable (%s%s); using local gate for %.0f s",
            type(exc).__name__,
            f" {status}" if status else "",
            RERANK_COOLDOWN_SECONDS,
        )
        return local()

    kept = [(c, p) for c, p in zip(candidates, fits) if p >= RERANK_THRESHOLD]
    if not kept:
        return retrieve.no_match_response()
    # Stable sort: equal probabilities keep the hybrid order.
    kept.sort(key=lambda pair: pair[1], reverse=True)
    hits = [
        retrieve.format_hit(
            c["name"], c["description"], p, c["agent"], max_chars=RERANK_DESCRIPTION_CHARS
        )
        for c, p in kept[: min(k, RERANK_MAX_HITS) if RERANK_MAX_HITS > 0 else k]
    ]
    return {"status": "ok", "hits": hits}
