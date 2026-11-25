"""Opt-in second-stage fit judgment by a swappable model.

Off by default: without ``SKILL_RAG_RERANK`` every search is the local hybrid
gate in ``retrieve.py`` and nothing leaves the machine.

When enabled, the local hybrid ranking only proposes a shortlist. A judge
(``skill_rag.judges``: ``jev``, ``openai``, or your own ``module:factory``)
returns, per shortlisted skill, the probability that it fits the query.

Two styles decide what is returned (``RERANK_STYLE``):

- ``candidates`` (default): every shortlisted skill at or above
  ``RERANK_FLOOR`` (0.5), best first, at most ``RERANK_SHOWN`` (8), as a
  ``candidates`` response with a short description each. The calling agent,
  a stronger selector than the judge once it can see the candidates, picks
  one or none. Measured, this loads the right skill about as often as putting
  every description in the agent's context, with a fraction of the wrong
  loads and of the context.
- ``single``: precision first. Only a skill at or above ``RERANK_THRESHOLD``
  (0.9) is returned, by default the single best one; below it, the best skill
  at or above ``RERANK_UNCERTAIN_FROM`` (0.7) is returned as ``uncertain``.

The built-in judges are cloud calls: they send the query text and
the shortlisted skills' names and descriptions to the provider. Skill bodies,
paths, and the rest of the corpus are never sent.

Up to ``RERANK_SCAN_MAX`` skills (default 500) the judge also scans the whole
corpus to build the shortlist, which puts the right skill among the
candidates far more often than the local ranking does, above all for Korean
requests. The scan sends every skill's name and the first 120 characters of
its description on every search. 0 turns it off.

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
# Largest corpus the judge scans whole to build the shortlist; 0 turns the
# scan off. A scan put the right skill in the top 16 for 95 to 97% of requests
# against 74 to 79% for the local shortlist. Under the ``single`` style that
# gain was small (docs/benchmarks/2026-11-25-scan-results.md); under
# ``candidates`` it is most of the result
# (docs/benchmarks/2026-11-25-candidates-results.md). A scan costs about 51
# input tokens per skill and was measured at 350 skills; the default covers
# corpora up to 500.
RERANK_SCAN_MAX = int(os.environ.get("SKILL_RAG_RERANK_SCAN_MAX", "500"))
# ``candidates`` or ``single``; see the module docstring.
RERANK_STYLE = os.environ.get("SKILL_RAG_RERANK_STYLE", "candidates").strip() or "candidates"
# ``candidates`` style: lowest probability shown, and how many skills at most.
# Chosen on a dev set and confirmed on a fresh test set; a floor of 0.1 or 8
# candidates without a floor raised wrong loads.
RERANK_FLOOR = float(os.environ.get("SKILL_RAG_RERANK_FLOOR", "0.5"))
RERANK_SHOWN = int(os.environ.get("SKILL_RAG_RERANK_SHOWN", "8"))

# Below the threshold the judge cannot tell right from wrong, but the calling
# agent can. On a fresh test set
# (docs/benchmarks/2026-11-25-agent2-results.md) showing the best skill in
# [0.7, 0.9) as an uncertain candidate raised the share of matching requests
# where a simulated agent loaded a useful skill from 60% to 67%, and wrong
# loads on requests with no matching skill from 4% to 8%. A value at or above
# the threshold turns this off.
RERANK_UNCERTAIN_FROM = float(os.environ.get("SKILL_RAG_RERANK_UNCERTAIN_FROM", "0.7"))
# Without a judge: return this many skills of the local ranking as uncertain
# candidates (up to LOCAL_DESCRIPTION_CHARS of description each) instead of
# the local gate's hits. Off (0) by default: in the same benchmark 3
# candidates halved wrong loads on requests with no matching skill (14% to 7%)
# but the agent also loaded a useful skill less often (70% to 63%), so it
# failed the test it had to pass to become the default.
LOCAL_CANDIDATES = int(os.environ.get("SKILL_RAG_LOCAL_CANDIDATES", "0"))
LOCAL_DESCRIPTION_CHARS = 300

# A skill the request names outright (``/name``, a quoted name, "the name
# skill"; see ``retrieve.explicit_matches``) is returned without a judgment:
# the user has already chosen. Set to 0 to judge such requests like any other.
EXPLICIT = os.environ.get("SKILL_RAG_EXPLICIT", "1") != "0"

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


SMALL_CORPUS = 50


def notes(indexed: int) -> list[str]:
    """What a user should know about this setup before relying on it.

    The figures are from docs/benchmarks/ (350 skills, simulated agent).
    """
    out = []
    state = readiness()
    if state == "off" or state.startswith("off ") or "unavailable" in state:
        out.append(
            "no judge model is active. At 350 skills, search without a judge loaded a useful "
            "skill for about 70% of requests; a harness that loads every skill description "
            "did so for about 94%. Set SKILL_RAG_RERANK=jev (README) where the MCP server "
            "runs, or keep loading skills natively."
        )
    elif 0 < RERANK_SCAN_MAX < indexed and RERANK_STYLE != "single":
        out.append(
            f"{indexed} skills exceed SKILL_RAG_RERANK_SCAN_MAX={RERANK_SCAN_MAX}: the judge "
            "sees the local shortlist only, which was not measured in the candidates style."
        )
    if 0 < indexed < SMALL_CORPUS:
        out.append(
            f"{indexed} skills are indexed. A list this short costs a harness about "
            f"{indexed * 100:,} tokens to load in full, so search saves little."
        )
    return out


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
    return search_traced(query, k=k, agent=agent, exclude=exclude)[0]


def search_traced(
    query: str, k: int = 5, agent: str | None = None, exclude: frozenset[str] = frozenset()
) -> tuple[dict, str]:
    """``search`` plus what actually produced the result: the judge's provider
    name, ``"explicit"`` when the request named the skill, or ``""`` when the
    local gate did (rerank off, cooldown, failure)."""
    if EXPLICIT:
        # Not filtered by ``exclude``: asking for a skill by name is a request
        # to have it, even if it was loaded earlier in the session.
        named = retrieve.explicit_matches(query)
        if named:
            hits = [
                retrieve.format_hit(
                    row["name"], row["description"], 1.0, row["agent"], max_chars=RERANK_DESCRIPTION_CHARS
                )
                for row in named[:k]
            ]
            return {"status": "ok", "hits": hits}, "explicit"

    def local() -> tuple[dict, str]:
        if LOCAL_CANDIDATES > 0 and query.strip() and retrieve.corpus_size() > 0:
            rows = retrieve.shortlist(query, min(k, LOCAL_CANDIDATES), exclude=exclude)
            if rows:
                return retrieve.uncertain_response(rows, LOCAL_DESCRIPTION_CHARS), ""
            return retrieve.no_match_response(), ""
        return retrieve.search(query, k=k, agent=agent, exclude=exclude), ""

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
            return retrieve.no_match_response(), RERANK_PROVIDER
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

    if RERANK_STYLE != "single":
        # ``k`` widens the shortlist above; it does not cap what is shown,
        # because callers pass a ``k`` chosen for the local gate.
        shown = sorted(
            ((c, p) for c, p in zip(candidates, fits) if p >= RERANK_FLOOR),
            key=lambda pair: pair[1],
            reverse=True,  # stable: equal probabilities keep the shortlist order
        )[: max(1, RERANK_SHOWN)]
        if not shown:
            return retrieve.no_match_response(), RERANK_PROVIDER
        return retrieve.candidates_response(shown, RERANK_DESCRIPTION_CHARS), RERANK_PROVIDER

    kept = [(c, p) for c, p in zip(candidates, fits) if p >= RERANK_THRESHOLD]
    if not kept:
        band = [(c, p) for c, p in zip(candidates, fits) if p >= RERANK_UNCERTAIN_FROM]
        if not band:
            return retrieve.no_match_response(), RERANK_PROVIDER
        # max keeps the first on ties, so equal probabilities keep the hybrid order.
        best = max(band, key=lambda pair: pair[1])[0]
        return retrieve.uncertain_response([best], RERANK_DESCRIPTION_CHARS), RERANK_PROVIDER
    # Stable sort: equal probabilities keep the hybrid order.
    kept.sort(key=lambda pair: pair[1], reverse=True)
    hits = [
        retrieve.format_hit(
            c["name"], c["description"], p, c["agent"], max_chars=RERANK_DESCRIPTION_CHARS
        )
        for c, p in kept[: min(k, RERANK_MAX_HITS) if RERANK_MAX_HITS > 0 else k]
    ]
    return {"status": "ok", "hits": hits}, RERANK_PROVIDER
