# Held-out corpus check and opt-in judge rerank

> Superseded as the headline result by `2026-11-24-scale-results.md`, which
> uses skills and queries nobody on this project wrote and shows markedly lower
> numbers. Read this one as an upper bound on easy, author-written queries.

Measured on 2026-11-24 on macOS (host, not Docker), `multilingual-e5-base`,
`jev-1.14.0`, single run per configuration.

## Why

Every threshold in `corpus.py` and the Korean hint table in `normalize.py` were
calibrated on the five-skill fixture corpus. This run asks how the shipped gate
behaves on a corpus and queries that played no part in that calibration, and
whether a second-stage fit judgment closes the gap.

## Setup

- Corpus: 40 skills installed for Claude Code on the test machine (26 AWS
  skills, 13 Anthropic skills, `find-skills`, `typesafe-ai`), symlinked into a
  temporary corpus directory. Descriptions run 120 to 1,026 characters and the
  AWS skills overlap heavily. The corpus is not in the repository.
- Queries: `bench/heldout/claude-skills.jsonl`, 110 rows written before any
  result was seen. 80 positives (one English and one Korean per skill) and 30
  no-match rows (10 off-topic, 20 near-domain such as Azure Functions, Firebase
  Auth, or SwiftUI, which share vocabulary with a skill that does not apply).
- Arms: `gate` is the default local path. `ungated` is the hybrid ranking with
  thresholds off (recall ceiling). `jev` is `SKILL_RAG_RERANK=jev`.
- Runner: `bench/jev_rerank_ab.py`.

## Results

| Corpus / arm | recall@1 | recall@5 | no-match accuracy | hits per positive | p50 / p95 |
|---|---:|---:|---:|---:|---:|
| Fixture, gate | 1.000 | 1.000 | 1.000 (5/5) | 1.28 | 24 / 59 ms |
| Held-out, gate | 0.688 | 0.762 | 0.533 (16/30) | 3.36 | 24 / 56 ms |
| Held-out, jev, 8 candidates | 0.925 | 0.925 | 1.000 (30/30) | 1.09 | 274 / 620 ms |
| Held-out, jev, 16 candidates | 0.988 | 0.988 | 1.000 (30/30) | 1.28 | 556 / 835 ms |

The gate fails in opposite directions by language on the held-out corpus:

| Held-out, gate | recall@5 | no-match accuracy |
|---|---:|---:|
| English | 1.000 | 0.133 (2/15) |
| Korean | 0.525 | 0.933 (14/15) |

English thresholds are too loose (a haiku request returns `amazon-bedrock`, a
Firebase Auth request returns `aws-auth`); Korean thresholds are too strict (9
of 40 positives return nothing, 10 more return only the wrong skills).

Jev arm details:

- Input tokens per request averaged 2,370 at 8 candidates and 4,364 at 16.
  Output tokens are not billed.
- At 8 candidates the fit probability was at least 0.76 for every correct
  skill and at most 0.12 on every no-match query; accuracy was identical for
  thresholds 0.2 through 0.7. At 16 candidates it was identical for 0.4 through
  0.7, and one no-match query passed at 0.2 and 0.3. The shipped 0.5 was fixed
  before the first run.
- Every remaining miss is a first-stage miss: the correct skill was not in the
  shortlist (6 Korean queries at 8 candidates, 1 at 16). Jev cannot recover a
  skill it is not shown.
- The fixture corpus also scored 1.000 on every metric with the jev arm.

Local-only shortlist checks (no API calls), positives only:

| Change | Correct skill in shortlist |
|---|---:|
| 8 candidates, `MAX_SEQ_LENGTH=64` (default) | 74/80 |
| 16 candidates | 79/80 |
| 24 candidates | 79/80 |
| 8 candidates, `MAX_SEQ_LENGTH=256` | 76/80 |
| 8 candidates, `MAX_SEQ_LENGTH=512` | 76/80 |

## Limits

- One author wrote all 110 queries with the skill descriptions in view. They
  are not real usage logs.
- One corpus, AWS-heavy, 40 skills. Not a claim about other collections.
- Single runs. The gate's Korean recall@1 moved between 0.425 and 0.475 across
  index rebuilds, apparently from RRF ties being broken by index row order;
  treat differences of one or two queries as noise.
- The 8-candidate row was measured with the experiment script before the
  feature existed; replaying its recorded probabilities through
  `skill_rag.rerank` reproduced it except for one query whose shortlist
  changed between index builds. The 16-candidate row is a live run of the
  shipped code path.
- Latency includes a network round trip from one location.

## Second run: 45 skills, two judges

After the first run, five skills were added to the corpus (`claude-api`,
`openai-docs`, `gemini-api-dev`, `uv`, `typescript-advanced-types`) and the
judge became swappable. `bench/heldout/claude-skills-45.jsonl` is the first
query set with three gold labels updated for the new skills plus 23 new rows
(13 positives, 10 near-domain no-match), again written before measuring: 133
queries, 95 positive and 38 no-match. Both judges ran through the shipped
`skill_rag.rerank` path with 16 candidates, threshold 0.5, and the same
question wording.

| Arm | recall@1 | recall@5 | no-match accuracy | hits per positive | response chars | p50 / p95 | input tokens per request |
|---|---:|---:|---:|---:|---:|---:|---:|
| gate | 0.726 | 0.779 | 0.395 (15/38) | 3.55 | 1,184 | 31 / 66 ms | none |
| `jev` (`jev-1.14.0`) | 0.979 | 0.979 | 1.000 (38/38) | 1.27 | 237 | 211 / 580 ms | 4,411 |
| `openai` (`gpt-6-luna`, Decisions API) | 0.968 | 0.968 | 0.947 (36/38) | 1.22 | 230 | 496 / 794 ms | 6,013 |

- "Response chars" is the mean size of the JSON `search_skills` returns, the
  context a search costs the agent. Judged hits carry 120-character
  descriptions and there are fewer of them, so both judges return about a
  fifth of what the gate does.
- The correct skill was in the 16-candidate shortlist for 93 of 95 positives.
  `jev` returned it first every time it was shortlisted, so both of its misses
  are first-stage misses (two Korean queries).
- `openai` missed one more positive (fit 0.04 for `import-memory` on "Import my
  memory export from ChatGPT") and returned `uv` for two no-match queries that
  mention Python but not uv (fit 0.76 and 0.89). Its other probabilities were
  more extreme than Jev's: at least 1.00 for 90% of correct skills.
- The two judges agreed on the first hit, or on returning nothing, for 130 of
  133 queries.
- `jev` accuracy was unchanged for thresholds 0.5 through 0.7 (one no-match
  query passes at 0.3 and 0.4); `openai` was unchanged from 0.2 through 0.7.
- On the 23 new rows alone the gate returned a skill for 9 of the 10 no-match
  queries; both judges returned none.
- Cost per search at list price for `openai` is about $0.0006 (input at $0.10
  per million tokens). TypeSafe pricing was not looked up.
- The native alternative, for scale: the harness lists every skill's
  description in each session, about 32,000 characters for these 45 skills,
  whether or not any search happens. skill-rag does not remove that listing.

The same limits apply: one author, one corpus, single runs, and the 23 new
rows were written by the person who had just chosen the five skills. Latency
differed between runs of the same judge (Jev p50 was 556 ms in the first run
and 211 ms here), so treat latency as indicative only.

## Conclusion

The default gate is fitted to the fixture and does not transfer. An opt-in fit
judgment over an ungated shortlist does, on this corpus, with either of two
independent judge models, at the cost of a cloud call. The default path stays local; see
`docs/superpowers/specs/2026-11-24-jev-rerank-opt-in.md`. The local gate's
calibration remains an open problem for users who keep rerank off.
