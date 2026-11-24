# Precision first: selection protocol (fixed before any new data existed)

Written and committed on 2026-11-24 while the confirmation run of
`2026-11-24-first-stage-protocol.md` was still in progress, before a dev
negative was generated or a decision rule tried.

## Why

The partial confirmation results show the whole-corpus scan finding the
expected skill more often (recall@5 up) while returning more skills and more
false alarms (strict no-match down). Returning a skill that does not fit costs
the agent a skill body's worth of tokens and can steer it wrong; returning
nothing costs only the help the skill would have given. The decision rule is
therefore chosen for precision first, and the scan stays on by default only if
it survives that rule.

## The first test set is finished

`bench/scale/queries.jsonl` has now been run twice (shipped configuration,
then the first-stage configuration). It is not run again for selection or for
the final numbers of this work.

## Dev set

Corpus: the 350-skill corpus. Judge: `jev`. Local first stage at the current
defaults (128 tokens, 300-character body prefix).

- Dev positives: the 178 existing dev queries.
- Dev negatives: 1 English and 1 Korean request for each of the 33 distractors
  that were never placed in any corpus, same generator, prompt, and name rule.
- Truth: the expected skill, plus the adjudicator of the scale protocol for
  any other returned skill ("fits" / "does not fit").

Dev outcomes may be inspected freely.

## What is measured for a decision rule

For each query the rule returns an ordered list of skills, possibly empty.

- **Junk rate on negatives**: the first returned skill does not fit.
- **Junk rate on positives**: the first returned skill is neither the expected
  skill nor judged to fit.
- **Useful rate on positives**: the first returned skill is the expected skill
  or judged to fit.
- Mean number of returned skills, requests, and input tokens per search.

## Candidates

1. Shortlist source: local hybrid top 16, or the judge's scan top 16.
2. Fit threshold: 0.5, 0.6, 0.7, 0.8, 0.9, 0.95.
3. Returned hits: up to `k`, or at most one.
4. Margin: return the first hit only if it leads the second by 0, 0.1, or 0.2.
5. Verification: one extra judge request about a top candidate that shows the
   opening 1,500 characters of the skill body and asks whether loading it would
   genuinely help with this specific request, same task on the same product,
   platform, or technology. Accept at 0.5, 0.7, or 0.9. Applied to the top
   candidate only, or to the top three taking the first that passes.

Other rules found while looking at dev outcomes may be tried and are listed in
the results.

## Selection rule

1. A configuration qualifies if its junk rate is at most 10% on dev negatives
   and at most 5% on dev positives.
2. Among qualifying configurations take the highest useful rate on positives.
   Within one percentage point of the best, take the fewest returned skills,
   then the fewest requests, then the fewest tokens.
3. If none qualifies, take the lowest junk rate on negatives among
   configurations whose useful rate on positives is at least 0.60, and say
   that the target was missed.

The selected configuration becomes the default behavior of the rerank path.

## Fresh test set, used once

Built only after the configuration is committed.

- Targets: 50 skills sampled with `random.Random(20261126)` from the 250
  members of the 350-skill corpus that were never a target in the first test
  set or the dev set. 2 English and 2 Korean requests each.
- Negatives: 50 skills sampled with the same generator from skills.sh
  candidates that never entered the pool, passing the scale protocol's content
  rules. 1 English and 1 Korean request each.
- Corpus: 350 skills only, since the targets are drawn from it.
- Arms: `gate`; `jev` before (local shortlist, threshold 0.5, no
  verification); `jev` after (the selected configuration); `openai` after.
- Scoring: strict recall@1 and no-match accuracy, the three rates above with
  adjudication, 95% bootstrap intervals.

No configuration is changed after this run. It is the result that the README
reports.
