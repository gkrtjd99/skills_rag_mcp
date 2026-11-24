# First-stage and precision results

Run on 2026-11-24 under two protocols that were each committed before their
data existed: `2026-11-24-first-stage-protocol.md` (`f791f22`) and
`2026-11-24-precision-protocol.md` (`52f5a02`). The configurations measured on
test data were committed before those runs (`20a55a1`, `50bf967`).

## Headline: fresh test set, 350 skills

293 queries nobody had seen: 196 for 50 skills in the corpus that were never a
target before, and 97 for 50 skills from 8 repositories that were never in the
pool. Run once. 95% bootstrap intervals in parentheses.

"Junk" means the first returned skill does not fit, as decided by the
adjudicator of the scale protocol. "Useful" means the first returned skill is
the expected one or is judged to fit.

| Arm | Junk on no-match requests | Junk on matching requests | Useful on matching requests | Skills returned | Response chars | p50 |
|---|---:|---:|---:|---:|---:|---:|
| gate | 0.887 (0.82-0.95) | 0.464 (0.40-0.54) | 0.505 (0.43-0.57) | 4.83 | 1,559 | 45 ms |
| `jev`, before (threshold 0.5, up to `k`) | 0.340 (0.25-0.43) | 0.133 (0.09-0.18) | 0.796 (0.74-0.85) | 1.95 | 426 | 207 ms |
| `jev`, shipped (threshold 0.9, one skill) | 0.093 (0.04-0.15) | 0.036 (0.02-0.07) | 0.679 (0.62-0.74) | 0.55 | 171 | 207 ms |
| `openai`, shipped | 0.268 (0.18-0.36) | 0.102 (0.06-0.14) | 0.796 (0.74-0.85) | 0.77 | 196 | 466 ms |

Strict scores of the same runs (expected skill only; nothing returned on
no-match requests): gate recall@1 0.42 and no-match 0.00; `jev` before 0.60 and
0.38; `jev` shipped 0.53 and 0.79; `openai` shipped 0.62 and 0.49.

- With `jev`, a skill that does not fit is now returned for about 9% of
  requests that have no matching skill, down from 34%, and for 4% of requests
  that have one, down from 13%. The price is that a useful skill is returned
  for 68% of matching requests instead of 80%.
- The dev set predicted this: 9.4%, 3.4%, and 67.4% on dev against 9.3%, 3.6%,
  and 67.9% here.
- **The shipped threshold was chosen with `jev` and does not carry over to
  `openai`**, whose probabilities sit closer to 0 and 1: at 0.9 it still
  returns a non-fitting skill for 27% of no-match requests. An `openai` user
  who wants the same precision needs a higher threshold, chosen on data.
- Korean is weaker than English: `jev` useful rate 0.58 against 0.78.
- `jev` used 3,427 input tokens per search, `openai` 5,112. No judge call
  failed.

## How the configuration was chosen

### First stage, on 178 dev queries at 350 skills

Share of dev queries whose expected skill is in the 16-candidate shortlist.

| Local first stage | In shortlist | Index time |
|---|---:|---:|
| 64 tokens, no body (previous default) | 0.742 | 1.3 s |
| 64 tokens, 300-character body prefix | 0.770 | 1.2 s |
| 128 tokens, no body | 0.775 | 2.3 s |
| **128 tokens, 300-character body prefix** | **0.787** | 2.2 s |
| 256 tokens, no body | 0.764 | 3.5 s |
| 256 tokens, 300-character body prefix | 0.742 | 4.2 s |

128 tokens with a body prefix was selected by the rule and is the new default.
The 4.5-point gain is 8 queries out of 178 and may be within sampling noise.
The public fixture evaluations are unchanged at 1.000.

Structural candidates, same metric: ranking every skill by the dense model
instead of the top 64 added about one point and was rejected under the
three-point rule; adding a BM25 ranker over name and description lowered it;
interleaving the two rankings instead of fusing them lowered it.

A whole-corpus scan by the judge was then tried as "another idea found on dev":

| Shortlist source | In shortlist | Input tokens per search |
|---|---:|---:|
| Local hybrid (previous default) | 0.742 | 0 |
| Judge scan, fit question with criteria, 200 characters | 0.955 | 51,500 |
| Judge scan, short question, 200 characters | 0.944 | 26,300 |
| Judge scan, short question, 120 characters | 0.921 | 20,700 |
| **Judge scan, bare question, 120 characters** | **0.972** | 17,800 |

### Confirmation of the scan on the first test set

Run once at threshold 0.5 with the scan on. At 350 skills `jev` strict
recall@5 rose from 0.725 to 0.873 and adjudicated recall@1 from 0.788 to
0.905, but it returned 4.2 skills per search instead of 1.8 and a
non-fitting first skill for 45% of no-match requests. The first stage stopped
being the limit; the judge's willingness to accept near-misses became it.

### Decision rule, on 242 dev queries (178 matching, 64 not)

| Shortlist | Threshold | Useful | Junk, matching | Junk, no-match | Returned |
|---|---:|---:|---:|---:|---:|
| local | 0.5 | 0.803 | 0.124 | 0.406 | 2.23 |
| local | 0.7 | 0.781 | 0.084 | 0.312 | 1.60 |
| local | 0.8 | 0.736 | 0.045 | 0.203 | 1.25 |
| **local** | **0.9** | **0.674** | **0.034** | **0.094** | 0.85 (0.61 as one skill) |
| local | 0.95 | 0.382 | 0.006 | 0.047 | 0.40 |
| scan | 0.5 | 0.826 | 0.174 | 0.516 | 6.42 |
| scan | 0.9 | 0.708 | 0.073 | 0.141 | 1.32 |

The rule required junk of at most 10% on no-match and 5% on matching requests,
then the highest useful rate. Local shortlist, threshold 0.9, one skill
returned is the result. The scan qualifies at no threshold without a further
step, so it is off by default.

## Deviations from the protocols

- The first dev measurement of the stage-1 grid sliced one long shortlist,
  which widened the dense candidate limit beyond what the rerank path uses.
  The script was corrected to call the shortlist at each size and the grid was
  rerun before anything was selected.
- The precision rule selected a verification step: one extra judge request
  showing the opening 1,500 characters of the top skill's body, accepted at
  0.7. It was better than no verification by one dev query in 64. It is not
  implemented, because it sends skill body text off the machine, which the
  rerank path has promised not to do. The selection was repeated over
  configurations that send no body text; the candidate list in the protocol
  should have excluded verification for that reason.
- "At most one returned skill" without verification was missing from the first
  grid and was added before the final selection; it changes the returned count
  only.
- 22 dev queries, 2 dev negatives, and 7 fresh-test queries named their skill
  twice and were dropped under the stated rule.

## Limits

One judge (`jev`) was used for every selection. Generated requests are not real
usage; the generator and the adjudicator are the same model family as the
`openai` judge. Adjudication was not spot-checked by a person. The fresh test
set has 97 no-match requests, so the junk rate on them is known to within
about five points either way. Its negatives come from 8 repositories whose
other skills are in the corpus, which is the hard case by design.

## What is still open

Sharper per-skill descriptions were tried next and did not help; see
`2026-11-24-cards-results.md`. Picking by comparison with a separate
"whether to return" signal, a score-list model, and a higher threshold for
`openai` did not help either; see `2026-11-24-structure-results.md`.

1. A threshold for `openai`, chosen on dev data with that judge.
2. Korean requests: the useful rate is 20 points below English.
3. Getting back the lost usefulness without the junk: the scan finds the right
   skill, so a stricter final decision on top of it may give both. The one
   variant tried on dev (scan plus body verification) matched the selected
   configuration at six times the tokens.
