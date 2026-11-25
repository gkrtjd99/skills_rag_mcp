# Whole-corpus scan with the agent in the loop: results (not adopted as the default)

Protocol: `2026-11-25-scan-protocol.md`, committed as `67c5de3` before the
dev set existed. Script: `bench/scale/scan_agent.py`. Dev set only; `test4`
was not built, as the protocol says for a negative result.

## Result

The scan arm missed the adoption bar by one request: 151 useful loads of 184
where 152 were needed (82.1% against a bar of 82.2%, L plus five points). It
met both junk limits. `SKILL_RAG_RERANK_SCAN_MAX` therefore stays 0 by
default. The measured effect is real enough to matter to some users and is
described below so they can turn the scan on knowingly.

`dev3`: 184 matching and 96 no-match requests, 350 skills, `jev`, primary
agent `gpt-6.1-terra`. Rates are of what the agent loads; L0 and S0 have no
agent and count the returned skill as loaded.

| Arm | Useful | Junk, matching | Junk, no-match | Useful, English | Useful, Korean | Shown on no-match |
|---|---|---|---|---|---|---|
| L local shortlist (shipped) | 77.2% | 4.3% | 1.0% (1) | 83.5% | 71.0% | 30.2% |
| S scan shortlist | 82.1% | 4.3% | 4.2% (4) | 83.5% | 80.6% | 79.2% |
| S9 scan shortlist, no uncertain band | 76.1% | 2.7% | 2.1% (2) | 79.1% | 73.1% | 28.1% |
| L0 local, no agent | 82.1% | 9.8% | 11.5% (11) | 86.8% | 77.4% | 30.2% |
| S0 scan, no agent | 88.0% | 11.4% | 47.9% (46) | 87.9% | 88.2% | 79.2% |

The expected skill was in the local shortlist for 79.3% of matching requests
and in the scan shortlist for 94.6%.

## What the numbers say

- The whole gain is on Korean requests: +9.6 points (71.0% to 80.6%), none on
  English. With the scan the two languages come out about equal. The local
  ranking is what holds Korean back.
- The agent is what makes the scan usable. Without it the scan returns a
  wrong skill for 47.9% of no-match requests; with it the agent loads a wrong
  one for 4.2%.
- The scan's gain comes through the uncertain band: with the band off (S9)
  the scan is no better than the shipped arm. The right skills the scan adds
  to the shortlist mostly score between 0.7 and 0.9.
- On no-match requests the scan shows a candidate far more often (79% against
  30%), almost always as uncertain, and the agent declines nearly all of
  them. That is extra metadata on those searches, about 120 characters.

## Costs

- About 17,800 input tokens per search for the scan at 350 skills (about
  $0.0007 at $0.042 per million), on top of about 3,400 for the fit
  judgment.
- Latency: scan p50 369 ms before the fit judgment's 185 ms.
- What is sent: every skill's name and the first 120 characters of its
  description on every search, instead of 16 names and descriptions. Bodies
  are still never sent.

## Limits

One request decides the outcome, and the set has 184 matching requests; the
true difference could be on either side of the bar. The simulated agent is
one model call with an empty context and not the model of a targeted harness.
Requests are model-written. Rates on `dev3` are higher across the board than
on earlier sets (the shipped arm scores 77.2% here and 60.3% on `test3`), so
only comparisons within this set mean anything. No confirmation agent and no
fresh test were run, so the Korean gain is a dev-set observation, not a
confirmed result.
