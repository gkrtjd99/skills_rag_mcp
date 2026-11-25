# Several candidates for the agent: results (adopted)

Protocol: `2026-11-25-candidates-protocol.md`, committed as `684e3b5` before
any list of candidates was shown to an agent. Script:
`bench/scale/candidates_agent.py`. Implementation committed as `9b30d37`
before the test run.

## Outcome

Adopted as the default with a judge: the judge scans every skill, the 16 it
ranks highest are judged for fit, and those at or above 0.5 are returned best
first, at most 8, for the calling agent to choose from. On a fresh test set a
simulated agent loaded a useful skill for 91.1% of matching requests against
74.9% under the single-skill rule, and a wrong skill for 9.4% of no-match
requests against 0.0%.

All rates are of what the simulated agent loads, judged by the adjudicator.

## Selection on dev3

184 matching and 96 no-match requests, 350 skills, `jev`, primary agent
`gpt-6.1-terra`. "Characters" is the metadata shown per request.

| Arm | Useful | Junk, matching | Junk, no-match | English | Korean | Characters |
|---|---|---|---|---|---|---|
| L single skill, local shortlist (shipped) | 77.2% | 4.3% | 1.0% (1) | 83.5% | 71.0% | 94 |
| S single skill, scan shortlist | 82.1% | 4.3% | 4.2% (4) | 83.5% | 80.6% | 120 |
| scan, 3 candidates, floor 0.1 | 92.4% | 3.8% | 6.2% (6) | 92.3% | 92.5% | 384 |
| scan, 3 candidates, floor 0.5 | 92.4% | 3.3% | 3.1% (3) | 92.3% | 92.5% | 347 |
| scan, 8 candidates, floor 0.1 | 95.7% | 3.3% | 9.4% (9) | 96.7% | 94.6% | 997 |
| **scan, 8 candidates, floor 0.5 (selected)** | 96.2% | 1.1% | 5.2% (5) | 96.7% | 95.7% | 652 |
| local, 3 candidates, floor 0.1 | 85.3% | 3.8% | 4.2% (4) | 91.2% | 79.6% | 315 |
| local, 3 candidates, floor 0.5 | 84.2% | 3.3% | 4.2% (4) | 90.1% | 78.5% | 204 |
| local, 8 candidates, floor 0.1 | 87.0% | 3.3% | 4.2% (4) | 91.2% | 82.8% | 529 |
| local, 8 candidates, floor 0.5 | 84.2% | 2.7% | 5.2% (5) | 90.1% | 78.5% | 236 |
| no judge, local top 8 | 79.3% | 4.9% | 4.2% (4) | 84.6% | 74.2% | 1,065 |
| no judge, local top 16 | 85.3% | 2.7% | 5.2% (5) | 91.2% | 79.6% | 2,121 |
| ALL every description in context | 97.3% | 2.2% | 36.5% (35) | 98.9% | 95.7% | about 33,750 tokens |

Nine of the ten configurations cleared the bar (L plus five points, 82.2%)
inside the junk limits. The two scan configurations with 8 candidates were
within one point of the best; the rule prefers the higher floor. With the
confirmation agent `gpt-6-astra` the selected configuration scored 95.1%
useful, 0.5% and 3.1% (3) junk.

## Fresh test

`test4`: 191 matching and 96 no-match requests, built after the
implementation was committed, run once.

| Arm | Useful | Junk, matching | Junk, no-match | English | Korean | Characters |
|---|---|---|---|---|---|---|
| L single skill, local shortlist | 74.9% | 3.1% | 0.0% (0) | 75.5% | 74.2% | 92 |
| S single skill, scan shortlist | 78.5% | 4.2% | 1.0% (1) | 76.6% | 80.4% | 114 |
| **scan, 8 candidates, floor 0.5** | 91.1% | 2.6% | 9.4% (9) | 92.6% | 89.7% | 650 |
| ALL every description in context | 94.8% | 5.2% | 54.2% (52) | 93.6% | 95.9% | about 33,750 tokens |

Confirmation agent: L 73.3% / 2.6% / 0.0%; candidates 92.7% / 1.6% / 5.2% (5).

The configuration passes: its useful rate is 16.2 points above L's and both
junk rates are inside the limits (junk on no-match at 9.4% is close to the
10% limit with the primary agent).

## What the numbers say

- The agent picks well from a short list. Eight judged candidates get within
  1 to 4 points of what it achieves with all 350 descriptions, at about 160
  tokens instead of 33,750, and with a fraction of the wrong loads (9.4%
  against 54.2% on the test).
- The scan matters as much as the list. The expected skill is in the scan
  shortlist for 94% of matching requests and in the local shortlist for 79 to
  86%; lists built from the local shortlist stop at 84 to 87% useful.
- The floor removes wrong loads without costing right ones: at 8 candidates,
  0.5 against 0.1 halves junk on no-match on dev3 at the same useful rate.
- Korean and English requests come out alike, as with the scan alone.
- It is not free. Under the single-skill rule the agent almost never loaded a
  wrong skill on a no-match request (0 to 1%); with candidates it does so for
  5 to 9%. A caller who cares more about that than about finding the skill
  can keep `SKILL_RAG_RERANK_STYLE=single`.
- Without a judge, showing the top 16 of the local ranking reaches 85% useful
  at about 2,100 characters. It was not selected and nothing changes for
  installs without a judge.

## Costs

Per search at 350 skills: about 17,800 judge input tokens for the scan and
about 3,400 for the fit judgment (about $0.0009 at $0.042 per million); scan
p50 370 ms and fit p50 185 ms; about 650 characters of metadata returned to
the agent. Every search sends the query and every skill's name and first 120
characters of description to the provider, plus the 16 shortlisted
descriptions in full. Bodies are never sent.

## Limits

One model call with an empty context stands in for an agent in the middle of
a task, and neither agent model is the one in the targeted harnesses; a real
agent may pick from a list more or less carefully. Requests are model-written
and never name a skill. The no-match requests come from skills near the
corpus, which raises wrong loads for every arm, most of all for ALL. Only
`jev` was measured: `openai` probabilities sit closer to 0 and 1, so a floor
of 0.5 may behave differently. One corpus size; the scan's cost grows with
the corpus and its default limit of 500 is beyond what was measured. dev3 was
used once before (for the scan comparison) and ten configurations were
compared on it; the test set was new.
