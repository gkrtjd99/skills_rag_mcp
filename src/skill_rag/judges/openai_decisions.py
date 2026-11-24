"""OpenAI Decisions judge: one ``predicate`` question per candidate.

``POST /v1/decisions`` returns, per question, the probability that the
condition is true. Needs ``OPENAI_API_KEY``; no extra package, because
``httpx`` is already a dependency. ``OPENAI_BASE_URL`` is honored.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor

from . import FIT_FALSE, FIT_TRUE, Candidate, JudgeConfig, batches, fit_question, scan_question

SCAN_BATCH = 400  # the Decisions API accepts at most 400 questions per request

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
        self.last_scan_usage: dict | None = None

    def unavailable_reason(self) -> str | None:
        if not os.environ.get("OPENAI_API_KEY"):
            return "OPENAI_API_KEY not set"
        return None

    def fits(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        # A predicate has no separate criteria field, so the yes/no definitions
        # travel inside the instructions.
        instructions = [
            f"{fit_question(c['name'], c['description'])}\n"
            f"Yes means: {FIT_TRUE}\nNo means: {FIT_FALSE}"
            for c in candidates
        ]
        fits, self.last_usage = self._ask(query, instructions)
        return fits

    def scan(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        """Coarse pass over many skills: one short predicate each."""
        parts = batches([scan_question(c["name"], c["description"]) for c in candidates], SCAN_BATCH)
        if len(parts) == 1:
            results = [self._ask(query, parts[0])]
        else:
            with ThreadPoolExecutor(min(4, len(parts))) as pool:
                results = list(pool.map(lambda part: self._ask(query, part), parts))
        self.last_scan_usage = {
            "model": results[0][1]["model"] if results else None,
            "input_tokens": sum(usage["input_tokens"] or 0 for _, usage in results),
        }
        return [p for values, _ in results for p in values]

    def _ask(self, query: str, instructions: Sequence[str]) -> tuple[list[float], dict]:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        body = self._post(
            base_url.rstrip("/") + "/decisions",
            {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            {
                "model": self._config.model or DEFAULT_MODEL,
                "input": f"Request: {query}",
                "questions": [
                    {"type": "predicate", "name": f"fit_{i}", "instructions": text}
                    for i, text in enumerate(instructions)
                ],
            },
            self._config.timeout,
        )
        usage = {
            "model": body.get("model"),
            "input_tokens": (body.get("usage") or {}).get("input_tokens"),
        }
        answers = {a.get("name"): a for a in body.get("answers", [])}
        values = []
        for i in range(len(instructions)):
            answer = answers.get(f"fit_{i}")
            if answer is None:
                raise ValueError("Decisions response is missing an answer")
            # A refused question carries no probability; treat it as not a fit
            # rather than failing the whole search.
            values.append(
                float(answer["probability"]) if answer.get("type") == "predicate" else 0.0
            )
        return values, usage
