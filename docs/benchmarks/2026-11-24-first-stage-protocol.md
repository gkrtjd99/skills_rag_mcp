# First-stage recall: selection protocol (fixed before any dev data existed)

Written and committed on 2026-11-24 before a dev query was generated or a
configuration tried. It extends `2026-11-24-scale-protocol.md`.

## Why

In the scale benchmark the expected skill was in the 16-candidate shortlist
for 96% of positives at 50 skills and 79% at 350. A judge cannot return a skill
it is not shown, so the shortlist is now the largest loss.

## Keeping the test set a test set

The 283 queries of the scale benchmark have been seen once, with the shipped
configuration. From here on they are used for exactly one more run: confirming
the configuration chosen below. Nothing is chosen, diagnosed, or tuned on
them, and their per-query outcomes are not inspected while choosing.

All choosing happens on a new dev set:

- Dev targets: 50 skills sampled with `random.Random(20261125)` from the first
  150 distractors, so each is in the 200- and 350-skill corpora and none is a
  test target or a held-out skill.
- Dev queries: 2 English and 2 Korean per dev target, from the same generator,
  prompt, and name rule as the scale protocol. Positives only; the first stage
  has no notion of no-match.
- Dev metric: the share of dev queries whose expected skill is in
  `retrieve.shortlist(query, K)`, measured locally with no judge and no API
  call. Primary: K = 16 on the 350-skill corpus.

## Stage 1: existing knobs

Six configurations, the cross of:

- `SKILL_RAG_MAX_SEQ_LENGTH`: 64 (shipped), 128, 256. This cap applies to both
  the indexed passage and the query.
- `SKILL_RAG_DENSE_BODY_CHARS`: 0 (shipped), 300.

Selection rule: take the highest primary metric. Among configurations within
one percentage point of the best, take the smallest sequence length, then the
smallest body prefix. It replaces the shipped default only if it beats (64, 0)
by at least three points; otherwise the defaults stay.

## Stage 2: structural change, only if needed

Entered only if the best stage-1 primary metric is under 0.90. Candidates,
each judged on the same dev metric against the stage-1 winner and kept only if
it adds at least three points:

1. A third ranker in the fusion: BM25 over name and description only, next to
   the existing BM25 over the full text, so a long body cannot bury a short
   trigger phrase.
2. Fusing by rank position within each list without the dense shortlist limit
   (every skill gets a dense rank).

Any other idea found while looking at dev misses may be tried on dev under the
same three-point rule and is listed in the results.

## Shortlist size

Reported for the chosen configuration at K = 8, 16, 24, 32. The shipped
default of 16 changes to 24 only if dev recall at 24 exceeds recall at 16 by at
least five points, because it raises judge input tokens by half.

## Confirmation

One run of the final configuration on the 283 test queries at 50, 100, 200,
and 350 skills with `gate`, `jev`, and `openai`, scored exactly as before and
reported next to the earlier results. If the final configuration equals the
shipped one, no run is made and that is reported.

## Costs to report

Index build time at 350 skills and warm query latency for each configuration,
since the 64-token cap was introduced to bound indexing time on a large corpus.
