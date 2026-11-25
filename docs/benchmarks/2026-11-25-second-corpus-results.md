# The shipped default on a second corpus: results (holds)

Protocol: `2026-11-25-second-corpus-protocol.md`, committed as `bcf3b58`
before any skill of the new corpus was downloaded. Script: `bench/scale2.py`.
Nothing was selected or changed; each arm ran once.

## Outcome

On 350 skills from repositories that nothing earlier had used, the shipped
default with `jev` loaded a useful skill for 88.8% of matching requests and a
wrong skill for 10.4% of no-match requests. The first corpus gave 91.1% and
9.4%. All three conditions fixed in advance for "holds" are met.

All rates are of what the simulated agent loads, judged by the adjudicator.

## Corpus B

- Candidates: ranks 601 to 2,600 of the skills.sh all-time listing on
  2026-11-25. After dropping entries already listed and every repository used
  before, 1,154 candidates from 219 repositories remained.
- Accepted under the unchanged rules: 756 from 173 repositories (231 dropped
  by the cap of 20 per repository, 72 without a `SKILL.md`, 60 duplicate ids,
  27 not on GitHub, 8 rejected by the parser or too short). 735 after
  dropping names that the first pool also has.
- Split, seed 20261201: 350 corpus skills from 107 repositories, 50 of them
  targets; 50 no-match sources outside the corpus. No further listing page
  was needed.
- Requests: 196 matching and 96 no-match (8 dropped by the name rule).

## Result

Primary agent `gpt-6.1-terra` unless noted.

| Arm | Useful | Junk, matching | Junk, no-match | English | Korean | In context |
|---|---|---|---|---|---|---|
| **C scan, 8 candidates, floor 0.5 (shipped)** | 88.8% | 4.6% | 10.4% (10) | 87.8% | 89.8% | 461 characters per search |
| C, confirmation agent `gpt-6-astra` | 93.4% | 1.0% | 9.4% (9) | 93.9% | 92.9% | 461 characters per search |
| L single skill (earlier default) | 71.4% | 4.1% | 4.2% (4) | 73.5% | 69.4% | 92 characters per search |
| ALL every description in context | 93.9% | 4.1% | 43.8% (42) | 94.9% | 92.9% | 35,147 tokens, always |

## Against the first corpus

Same arms, same agent, `test4` on the first corpus and `b1` on corpus B.

| Arm | Useful, first | Useful, B | Junk no-match, first | Junk no-match, B |
|---|---|---|---|---|
| C (shipped) | 91.1% | 88.8% | 9.4% (9 of 96) | 10.4% (10 of 96) |
| L | 74.9% | 71.4% | 0.0% (0) | 4.2% (4) |
| ALL | 94.8% | 93.9% | 54.2% (52) | 43.8% (42) |

## The conditions fixed in advance

| Condition | Required | Measured | Met |
|---|---|---|---|
| C useful | at least 86.1% | 88.8% | yes |
| C junk on no-match | at most 13% | 10.4% | yes |
| C junk on no-match below half of ALL's | below 21.9% | 10.4% | yes |

## What else the records show

- The expected skill was in the judge's scan shortlist for 99.0% of matching
  requests and in the local shortlist for 83.2%. It was in the scan shortlist
  with a fit of at least 0.5 for 90.3%.
- Scan: 18,295 input tokens on average, 377 ms at the median; fit judging
  187 ms at the median.
- C showed something for 86.5% of no-match requests; the agent declined most
  of them.

## Reading it

- The gap to ALL in useful loads is 5.1 points here and 3.7 on the first
  corpus. Search with a judge finds somewhat fewer right skills than loading
  everything on both.
- Wrong loads on no-match requests are about a quarter of ALL's here (10.4%
  against 43.8%) and about a sixth on the first corpus.
- C's 10.4% is one request above the 10% limit that was used when the
  configuration was adopted. It is inside the three-point allowance fixed for
  this run, and both corpora sit at the limit, so the limit is where this
  configuration operates, not a margin it clears.
- L dropped by a similar amount (3.5 points) and ALL by less (0.9), so part
  of C's 2.3-point drop is this corpus being harder for search, not
  settings fitted to the first one. With 196 requests the drop itself is
  inside the noise.

## Limits

One more pool from the same listing site, at lower install ranks. The
generator, both agent models, and the adjudicator are the same as before, so
anything those have in common with each other is untested. The agent is one
model call with an empty context. 350 skills and `jev` only.
