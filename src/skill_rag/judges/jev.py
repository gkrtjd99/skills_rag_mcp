"""TypeSafe Jev judge: one Noul per candidate in a single request.

Needs the ``rerank`` extra (``typesafe-sdk``) and ``TYPESAFE_API_KEY``.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor

from . import FIT_FALSE, FIT_TRUE, Candidate, JudgeConfig, batches, fit_question, scan_question

# Well inside the 64k-token request limit at about 51 tokens per skill.
SCAN_BATCH = 400


class JevJudge:
    name = "jev"
    destination = "TypeSafe API"

    def __init__(self, config: JudgeConfig):
        self._config = config
        self._client = None
        #: ``{"model", "input_tokens"}`` of the most recent call, for benchmarks.
        self.last_usage: dict | None = None
        self.last_scan_usage: dict | None = None

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

    def scan(self, query: str, candidates: Sequence[Candidate]) -> list[float]:
        """Coarse pass over many skills: one short Noul each, no criteria."""
        client = self._get_client()
        kwargs = {"model": self._config.model} if self._config.model else {}

        def one(batch: Sequence[Candidate]):
            questions = {
                f"s{i}": {
                    "type": "noul",
                    "instructions": scan_question(c["name"], c["description"], "`request`"),
                }
                for i, c in enumerate(batch)
            }
            response = client.system_one({"request": query}, questions, **kwargs)
            tokens = getattr(getattr(response, "usage", None), "input_tokens", None) or 0
            return [float(response.nouls[f"s{i}"].noul) for i in range(len(batch))], tokens, getattr(response, "model", None)

        parts = batches(candidates, SCAN_BATCH)
        if len(parts) == 1:
            results = [one(parts[0])]
        else:
            with ThreadPoolExecutor(min(4, len(parts))) as pool:
                results = list(pool.map(one, parts))
        self.last_scan_usage = {
            "model": results[0][2] if results else None,
            "input_tokens": sum(tokens for _, tokens, _ in results),
        }
        return [p for values, _, _ in results for p in values]
