"""OpenAI Decisions judge: one ``predicate`` question per candidate.

``POST /v1/decisions`` returns, per question, the probability that the
condition is true. Needs ``OPENAI_API_KEY``; no extra package, because
``httpx`` is already a dependency. ``OPENAI_BASE_URL`` is honored.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence

from . import FIT_FALSE, FIT_TRUE, Candidate, JudgeConfig, fit_question

DEFAULT_MODEL = "gpt-6-luna"  # the only model the Decisions API accepts today


def _post(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    import httpx  # lazy: keeps importing this module free of network stacks

    response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


class OpenAIDecisionsJudge:
    name = "openai"
    destination = "OpenAI API"

    def __init__(self, config: JudgeConfig, post: Callable[..., dict] = _post):
        self._config = config
        self._post = post
        #: ``{"model", "input_tokens"}`` of the most recent call, for benchmarks.
        self.last_usage: dict | None = None

    def unavailable_reason(self) -> str | None:
        if not os.environ.get("OPENAI_API_KEY"):
            return "OPENAI_API_KEY not set"
        return None

    def fits(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        # A predicate has no separate criteria field, so the yes/no definitions
        # travel inside the instructions.
        questions = [
            {
                "type": "predicate",
                "name": f"fit_{i}",
                "instructions": (
                    f"{fit_question(c['name'], c['description'])}\n"
                    f"Yes means: {FIT_TRUE}\nNo means: {FIT_FALSE}"
                ),
            }
            for i, c in enumerate(candidates)
        ]
        body = self._post(
            base_url.rstrip("/") + "/decisions",
            {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            {
                "model": self._config.model or DEFAULT_MODEL,
                "input": f"Request: {query}",
                "questions": questions,
            },
            self._config.timeout,
        )
        self.last_usage = {
            "model": body.get("model"),
            "input_tokens": (body.get("usage") or {}).get("input_tokens"),
        }
        answers = {a.get("name"): a for a in body.get("answers", [])}
        fits = []
        for i in range(len(candidates)):
            answer = answers.get(f"fit_{i}")
            if answer is None:
                raise ValueError("Decisions response is missing an answer")
            # A refused question carries no probability; treat it as not a fit
            # rather than failing the whole search.
            fits.append(
                float(answer["probability"]) if answer.get("type") == "predicate" else 0.0
            )
        return fits
