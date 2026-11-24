"""TypeSafe Jev judge: one Noul per candidate in a single request.

Needs the ``rerank`` extra (``typesafe-sdk``) and ``TYPESAFE_API_KEY``.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Sequence

from . import FIT_FALSE, FIT_TRUE, Candidate, JudgeConfig, fit_question


class JevJudge:
    name = "jev"
    destination = "TypeSafe API"

    def __init__(self, config: JudgeConfig):
        self._config = config
        self._client = None
        #: ``{"model", "input_tokens"}`` of the most recent call, for benchmarks.
        self.last_usage: dict | None = None

    def unavailable_reason(self) -> str | None:
        if importlib.util.find_spec("typesafe_sdk") is None:
            return "typesafe-sdk not installed (uv sync --extra rerank)"
        if not os.environ.get("TYPESAFE_API_KEY"):
            return "TYPESAFE_API_KEY not set"
        return None

    def _get_client(self):
        if self._client is None:
            # Imported lazily: the SDK is an optional extra and the default
            # path must import and run without it.
            from typesafe_sdk import RetryPolicy, TypeSafeClient

            self._client = TypeSafeClient(
                timeout=self._config.timeout,
                retry=RetryPolicy(max_retries=1, timeout=self._config.timeout),
            )
        return self._client

    def fits(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        # Positional ids: skill names are user data and need not be unique or
        # safe as keys. Question ids are never sent to the model.
        questions = {
            f"fit_{i}": {
                "type": "noul",
                "instructions": fit_question(c["name"], c["description"]),
                "criteria": {"true": FIT_TRUE, "false": FIT_FALSE},
            }
            for i, c in enumerate(candidates)
        }
        kwargs = {"model": self._config.model} if self._config.model else {}
        response = self._get_client().system_one({"request": query}, questions, **kwargs)
        usage = getattr(response, "usage", None)
        self.last_usage = {
            "model": getattr(response, "model", None),
            "input_tokens": getattr(usage, "input_tokens", None),
        }
        return [float(response.nouls[f"fit_{i}"].noul) for i in range(len(candidates))]
