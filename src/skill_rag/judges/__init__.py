"""Pluggable fit judges for the opt-in rerank stage.

A judge answers one question per shortlisted skill: how likely is it that this
skill is the right one to load for the query. ``rerank.py`` owns everything
else (shortlist, threshold, ordering, fail-open, cooldown), so supporting a new
model is one small class.

To add a provider, implement ``Judge`` and either register it in ``BUILTIN`` or
point ``SKILL_RAG_RERANK`` at ``package.module:factory``. The factory is called
once with a ``JudgeConfig`` and must return a ``Judge``.
"""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol, TypedDict


class Candidate(TypedDict):
    """One shortlisted skill, as produced by ``retrieve.shortlist``."""

    name: str
    description: str
    agent: str


@dataclass(frozen=True, slots=True)
class JudgeConfig:
    """Provider-independent settings. Providers read their own credentials."""

    model: str = ""  # empty: the provider's default model
    timeout: float = 5.0  # seconds for the whole judgment


class Judge(Protocol):
    """A model that scores how well each candidate skill fits a query."""

    #: Provider id shown in ``skill-rag status``.
    name: str
    #: Where the query and candidate text are sent ("" when nothing leaves the
    #: machine). Shown to the user; keep it honest.
    destination: str

    def unavailable_reason(self) -> str | None:
        """Why ``fits`` cannot work right now, from local checks only (missing
        package or credential). ``None`` when it looks ready. Must not perform
        a request."""

    def fits(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        """Probability in [0, 1] that each candidate is the right skill for
        ``query``, in the same order as ``candidates``.

        Each candidate must be judged on its own, so a skill's value does not
        depend on which other skills were shortlisted. Raise on any failure;
        the caller falls back to the local gate. Send only the query and the
        candidates' names and descriptions.
        """


#: Built-in providers: ``SKILL_RAG_RERANK`` value -> ``module:factory``.
BUILTIN = {
    "jev": "skill_rag.judges.jev:JevJudge",
    "openai": "skill_rag.judges.openai_decisions:OpenAIDecisionsJudge",
}

# Bound request size on corpora with very long frontmatter descriptions.
MAX_DESCRIPTION_CHARS = 1500

FIT_TRUE = (
    "The skill's stated scope directly covers the specific thing the request "
    "asks for, on the same product or platform."
)
FIT_FALSE = (
    "The request is about something else, concerns a different product or "
    "platform, or only shares vocabulary with the skill."
)


def fit_question(name: str, description: str) -> str:
    """The one question every provider asks, so providers stay comparable."""
    return (
        f"Is the skill '{name}' the right documented procedure to load for "
        "the task in the request? The request may be written in any language. "
        f"Skill description: {description[:MAX_DESCRIPTION_CHARS]}"
    )


def is_known(spec: str) -> bool:
    """True for a built-in provider id or a ``module:factory`` path."""
    return spec in BUILTIN or ":" in spec


def load(spec: str, config: JudgeConfig) -> Judge:
    """Instantiate the judge named by ``spec``. Raises if it cannot be built."""
    module_name, _, attr = BUILTIN.get(spec, spec).partition(":")
    if not module_name or not attr:
        raise ValueError(
            f"unknown rerank provider {spec!r}; use one of {sorted(BUILTIN)} "
            "or 'package.module:factory'"
        )
    judge = getattr(importlib.import_module(module_name), attr)(config)
    if not callable(getattr(judge, "fits", None)):
        raise TypeError(f"{spec!r} did not produce a judge with fits()")
    return judge


def checked(values: Sequence[float], expected: int) -> list[float]:
    """Validate a provider's raw output before it is used as a decision."""
    probabilities = [float(v) for v in values]
    if len(probabilities) != expected:
        raise ValueError(f"judge returned {len(probabilities)} values for {expected} candidates")
    if any(not 0.0 <= p <= 1.0 for p in probabilities):
        raise ValueError("judge returned a value outside [0, 1]")
    return probabilities
