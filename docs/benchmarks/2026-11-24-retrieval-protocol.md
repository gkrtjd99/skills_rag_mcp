# First stage, second attempt: selection protocol (fixed before any synthetic request or new embedding existed)

Written and committed on 2026-11-24 before a synthetic request was generated,
before `BAAI/bge-m3` was downloaded, and before any new shortlist was built. It
extends `2026-11-24-precision-protocol.md`.

## Why

Four attempts to improve the final decision failed on dev
(`2026-11-24-cards-results.md`, `2026-11-24-structure-results.md`). A different
loss is untouched: for 16% of matching dev requests the right skill is not
among the 16 candidates the judge sees (11% English, 21% Korean). Research
points at two changes with measured support elsewhere: indexing synthetic user
requests per skill, and a stronger multilingual embedder (one Korean-to-English
study has `multilingual-e5-base` well behind `bge-m3`).

## Conditions

Two embedders by three index contents, everything else as shipped (128-token
cap, 300-character body prefix, BM25 over the full text, reciprocal rank
fusion, dense candidate limit as in the rerank path):

| | No synthetic requests | Synthetic requests from the description | Synthetic requests from the body |
|---|---|---|---|
| `intfloat/multilingual-e5-base` | E0 (shipped) | E1 | E2 |
| `BAAI/bge-m3` | B0 | B1 | B2 |

Synthetic requests: 5 English and 5 Korean per skill, written by
`gpt-6.1-terra` (not the model that wrote the dev requests). Developer message,
verbatim, with the bracketed part depending on the variant:

> You are given [the name and description | the name, description, and
> instructions] of an agent skill. Write 5 requests in English and 5 in Korean
> that a user might type to an AI agent when this skill is what they need.
> Each is one sentence describing the user's own task, in varied wording,
> without the skill's name. Use only what the text says the skill covers.

Each synthetic request is embedded as a query-side text and stored as an extra
vector of its skill; a skill's dense score is the maximum over its own passage
vector and its synthetic vectors. The synthetic requests are also appended to
the text BM25 indexes.

## What is measured

On the 242 dev requests at 350 skills, for each condition:

- the share of matching requests whose right skill is in the top 16, overall
  and by language (reported, not used for selection);
- end to end with the shipped decision unchanged (`jev` yes/no at least 0.9,
  one skill): useful rate, junk on matching requests, junk on no-match
  requests, by the same adjudicator. Yes/no probabilities already recorded for
  a (request, skill) pair are reused; only pairs that are new to a shortlist
  are asked.

## Selection, adoption, confirmation

A condition qualifies if its junk rates are at most 10% on no-match and 5% on
matching requests. It is a candidate for adoption only if its useful rate
exceeds E0's by at least five points. Among candidates within one point of the
best, the cheapest wins, in the order E1, E2, B0, B1, B2 (no new model before a
new model; no body text sent to a provider before body text).

An adopted condition is implemented, committed, and run once on a fresh test
set against E0. It stays only if its useful rate is higher there and neither
junk rate is more than three points higher.

## A confound stated in advance

Dev requests and the fresh test requests are written by a model from skill
bodies. Synthetic requests written from the same bodies (E2, B2) share that
origin, so their gain on this benchmark is an upper bound on their gain with
real requests, and the fresh test cannot remove the bias. Description-based
synthetic requests (E1, B1) add no body content and are the cleaner test.
If only body-based conditions qualify, that is reported as unresolved by this
benchmark rather than as a win.

## Costs to report

Index build time and warm query latency per condition, model size and memory
for `bge-m3`, and generation tokens for the synthetic requests.
