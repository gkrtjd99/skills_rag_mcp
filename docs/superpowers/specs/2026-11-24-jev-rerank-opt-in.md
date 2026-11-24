# Opt-in Rerank With Swappable Judges

Date: 2026-11-24
Status: Implemented and measured

## Decision

Add an opt-in second stage, `SKILL_RAG_RERANK=<provider>`, that replaces the
threshold gate with a per-candidate fit probability from a judge model. It is
off by default, and the default path is unchanged and fully local.

Built-in providers are `jev` (TypeSafe Jev) and `openai` (OpenAI Decisions
API). Any other model can be plugged in as `package.module:factory`.

This is a deliberate, maintainer-approved exception to the Local-First belief
and to the former "LLM-based scoring is out of scope" line. `core-beliefs.md`
states the exception and its limits.

## Evidence

On a 45-skill corpus and 133 queries that were not used for calibration, the
shipped gate scored recall@1 0.726 and no-match accuracy 0.395, against 1.000
and 1.000 on the fixture. With rerank the same queries scored 0.979 / 1.000
(`jev`) and 0.968 / 0.947 (`openai`), and the mean search response shrank from
1,184 to about 235 characters. Full numbers, method, and limits:
`docs/benchmarks/2026-11-24-heldout-jev-rerank.md`.

Those queries were author-written. A later benchmark with pre-registered rules,
community skills, and model-written queries confirms the direction but not the
size: at 350 skills strict recall@1 is 0.450 for the gate and 0.672 / 0.646 for
`jev` / `openai`, with frequent false alarms on near-miss requests
(`docs/benchmarks/2026-11-24-scale-results.md`).

## Behavior

1. `retrieve.shortlist` returns the top `SKILL_RAG_RERANK_CANDIDATES` (default
   16, never fewer than `k`) by fused hybrid rank with every threshold off.
2. The judge returns one probability per candidate from a single request. Each
   candidate is judged independently with the same question: is this skill the
   right documented procedure for the request.
3. Candidates at or above `SKILL_RAG_RERANK_THRESHOLD` (default 0.5) are
   returned in order of probability. The hit `score` is that probability, and
   the hit `description` is capped at `SKILL_RAG_RERANK_DESCRIPTION_CHARS`
   (default 120). If none qualify the response is the usual `no_match`.
4. `skip`, empty-query, and empty-corpus responses are decided locally before
   any request.

Response shapes are unchanged. The `score` field keeps its range but changes
meaning when rerank is on: a per-skill probability, comparable across queries,
instead of a query-relative fused rank.

## Judge interface

`skill_rag/judges/__init__.py` defines the contract; `rerank.py` owns policy
(shortlist, threshold, ordering, output validation, fail-open, cooldown), so a
provider is only a scorer:

```python
class Judge(Protocol):
    name: str          # provider id
    destination: str   # where query + candidate text is sent; "" if local
    def unavailable_reason(self) -> str | None: ...   # local checks only
    def fits(self, query, candidates) -> list[float]: ...  # one P in [0,1] each
```

A factory receives `JudgeConfig(model, timeout)` and returns a judge.
Providers read their own credentials. `rerank.judge` rejects output of the
wrong length or outside [0, 1], which counts as a failure. All providers share
`judges.fit_question` so their numbers are comparable.

## Failure handling

Any error (unknown provider, SDK not installed, key unset, no credits,
timeout, API error, malformed output) returns the local gate's answer for that
query and keeps rerank off for `SKILL_RAG_RERANK_COOLDOWN` seconds (default
60). The warning logged names the exception type and HTTP status only.
`skill-rag status` reports whether rerank is off, ready (and where data goes),
or unavailable and why.

## Privacy

With rerank on, each search sends the query text and the names and
descriptions of the shortlisted skills to the judge's provider. Skill bodies,
filesystem paths, and the rest of the corpus are not sent. With rerank off
nothing leaves the machine.

## Dependencies

- `jev`: `typesafe-sdk`, an optional extra (`uv sync --extra rerank`), imported
  only when that judge is used.
- `openai`: no new package. It calls `POST /v1/decisions` with `httpx`, which
  `mcp` already required and is now declared directly.

The default install, tests, and offline runtime need neither API.

## Not changed

- The local gate's thresholds and Korean hint table. The benchmark shows they
  do not transfer to an unseen corpus; recalibrating them is separate work.
- Native skill listing. Harnesses still load every collected skill's
  description each session (about 32,000 characters for the 45-skill corpus),
  which is far larger than any search response. Removing that needs a
  lifecycle change (moving skills out of harness directories), not a
  retrieval change.
