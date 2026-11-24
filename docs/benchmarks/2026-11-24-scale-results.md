# Scale benchmark results

Run on 2026-11-24 under the protocol fixed beforehand in
`2026-11-24-scale-protocol.md` (commit `0c57561`, made before any skill was
downloaded or query generated). Raw outputs are under `var/bench/scale/`
(not committed); the skill manifest, split, and queries are in `bench/scale/`.

## What was measured

- Pool: 433 skills from 79 GitHub repositories, accepted in list order from
  the 745 entries on skills.sh's trending and all-time lists. Rejected: 96
  repeated skill ids, 114 over the 20-per-repository cap, 54 with no
  `SKILL.md` found, 33 non-GitHub sources, 15 too short.
- Split (seed 20261124): 50 targets in every corpus, 50 held out of every
  corpus, 333 distractors. Corpus sizes 50, 100, 200, 350.
- Queries: 283, written by `gpt-6.2-sol` from skill bodies with the
  frontmatter removed. 189 positives (targets) and 94 negatives (held-out
  skills), 138 English and 145 Korean. The same queries at every size.
- Arms at shipped defaults: `gate`, `jev` (`jev-1.14.0`), `openai`
  (`gpt-6-luna`). No judge call failed or fell back.

## Results

95% bootstrap intervals in parentheses. "adj." columns are the adjudicated
metrics defined in the protocol: a first hit that is not the expected skill
still counts if an independent model judges that it genuinely fits.

| Skills | Arm | recall@1 | recall@5 | no-match | adj. recall@1 | adj. no-match | resp. chars | p50 ms |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 50 | gate | 0.619 (0.55-0.69) | 0.767 | 0.064 (0.02-0.12) | 0.646 (0.58-0.71) | 0.160 (0.10-0.23) | 1361 | 37 |
| 50 | jev | 0.862 (0.81-0.91) | 0.889 | 0.351 (0.26-0.45) | 0.915 (0.87-0.95) | 0.574 (0.47-0.67) | 336 | 210 |
| 50 | openai | 0.857 (0.80-0.90) | 0.915 | 0.394 (0.30-0.49) | 0.915 (0.87-0.95) | 0.638 (0.54-0.73) | 361 | 473 |
| 100 | gate | 0.529 (0.46-0.60) | 0.741 | 0.032 (0.00-0.07) | 0.577 (0.51-0.65) | 0.160 (0.09-0.23) | 1474 | 33 |
| 100 | jev | 0.841 (0.79-0.89) | 0.862 | 0.277 (0.19-0.37) | 0.899 (0.86-0.94) | 0.585 (0.48-0.68) | 326 | 201 |
| 100 | openai | 0.794 (0.73-0.85) | 0.889 | 0.309 (0.22-0.40) | 0.878 (0.83-0.92) | 0.691 (0.60-0.79) | 362 | 452 |
| 200 | gate | 0.460 (0.39-0.53) | 0.667 | 0.021 (0.00-0.05) | 0.519 (0.45-0.59) | 0.170 (0.10-0.24) | 1495 | 37 |
| 200 | jev | 0.730 (0.67-0.79) | 0.783 | 0.255 (0.17-0.35) | 0.836 (0.78-0.88) | 0.628 (0.53-0.72) | 346 | 202 |
| 200 | openai | 0.693 (0.63-0.76) | 0.810 | 0.330 (0.24-0.44) | 0.820 (0.76-0.87) | 0.713 (0.62-0.81) | 373 | 462 |
| 350 | gate | 0.450 (0.38-0.52) | 0.635 | 0.021 (0.00-0.05) | 0.503 (0.43-0.57) | 0.191 (0.12-0.27) | 1550 | 38 |
| 350 | jev | 0.672 (0.60-0.74) | 0.725 | 0.266 (0.18-0.36) | 0.788 (0.73-0.84) | 0.702 (0.61-0.80) | 392 | 206 |
| 350 | openai | 0.646 (0.58-0.71) | 0.741 | 0.319 (0.22-0.41) | 0.788 (0.73-0.84) | 0.723 (0.63-0.81) | 398 | 469 |

By language, strict recall@1 / adjudicated recall@1:

| Skills | Arm | English | Korean |
|---:|---|---:|---:|
| 50 | gate | 0.663 / 0.696 | 0.577 / 0.598 |
| 50 | jev | 0.880 / 0.935 | 0.845 / 0.897 |
| 50 | openai | 0.880 / 0.946 | 0.835 / 0.887 |
| 350 | gate | 0.522 / 0.576 | 0.381 / 0.433 |
| 350 | jev | 0.685 / 0.793 | 0.660 / 0.784 |
| 350 | openai | 0.674 / 0.793 | 0.619 / 0.784 |

Adjudication covered 643 distinct (query, first hit) pairs; 143 were judged to
fit.

## What the numbers say

- **Both judges beat the gate at every size, and the intervals do not
  overlap.** At 350 skills strict recall@1 is 0.450 for the gate against 0.672
  (`jev`) and 0.646 (`openai`). The gate returns something for 98% of
  negatives.
- **The two judges are not distinguishable here.** Their intervals overlap on
  every metric at every size. `jev` answered in about 205 ms, `openai` in
  about 465 ms.
- **Accuracy falls as the corpus grows, mostly in the first stage.** The
  expected skill was in the 16-candidate shortlist for 96.3%, 93.7%, 85.7%,
  and 78.8% of positives at 50, 100, 200, and 350 skills. At 350, 40 of the
  62 positives `jev` missed were not in the shortlist at all; a judge cannot
  recover a skill it is not shown.
- **False alarms are common on near-miss requests.** After adjudication,
  `jev` still returned a skill that does not fit for 40 of 94 negatives at 50
  skills and 28 of 94 at 350 (`openai`: 34 and 26). 43 of the 50 held-out
  skills have a sibling from the same repository in the 350-skill corpus, and
  12 of the 28 `jev` false alarms there were such siblings; others were
  general-purpose process skills.
- **Strict no-match understates the judges.** Many "negatives" have a
  genuinely fitting skill in the corpus: adjudicated no-match is 0.57 to 0.72
  for the judges against 0.27 to 0.39 strict.
- **Responses stay small.** Judged searches return 330 to 400 characters
  against 1,360 to 1,550 for the gate.
- **The shipped threshold is not the best one for false alarms.** Printed as
  sensitivity only, not adopted: at 350 skills raising the `jev` threshold
  from 0.5 to 0.8 moves strict no-match from 0.27 to 0.50 while recall@1 goes
  from 0.67 to 0.63. `openai` barely moves (0.32 to 0.36).

## Against the earlier, author-written benchmark

`2026-11-24-heldout-jev-rerank.md` reported recall@1 0.979 and no-match
accuracy 1.000 for `jev` on 45 skills. Those queries were written by one
person with the skill descriptions in view, and its no-match queries named
other products outright. Here, at a comparable 50 skills, the same
configuration scores 0.862 strict (0.915 adjudicated) and 0.351 strict (0.574
adjudicated). Treat the earlier numbers as an upper bound on an easy set, and
these as the ones to plan with.

## Deviations from the protocol

- The largest size is 350, not 400: 433 skills were accepted and the protocol's
  rule for a pool under 450 applies.
- 283 queries, not 300: 17 generated requests named their skill twice and
  were dropped under the stated rule.
- The benchmark runner does not carry the `from_skill` field into its output.
  The same-repository analysis above joins it back from `queries.jsonl`; no
  metric depends on it.
- Judge token usage for these runs was not captured.

## Limits

As accepted in the protocol: the query generator, the adjudicator, and the
`openai` judge share a vendor; generated requests are not real usage; trending
lists include near-copies; single run per configuration. Adjudication is one
model's opinion and was not spot-checked by a person. Negatives come from
skills of the same repositories as the corpus, which makes them harder than
unrelated requests and is why they were chosen.

## Follow-ups this points to

1. First-stage recall at scale is now the largest loss. Candidates: a wider
   shortlist, a longer embedding window than 64 tokens, or a judge-based first
   stage. Each needs its own measurement on this set.
2. A higher or per-provider threshold would cut false alarms; it has to be
   chosen on data other than this set and then checked here.
3. Sibling skills from one repository need a tie-breaker, for example asking
   the judge to choose among the kept candidates.
