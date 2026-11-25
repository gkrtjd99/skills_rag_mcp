# Letting the agent decide the uncertain band: results (not adopted)

Protocol: `2026-11-25-agent-protocol.md`, committed before any agent decision
was collected (`9e4eba1`). Script: `bench/scale/agent_dev.py`. Dev set only;
no test set was used, as the protocol says for a negative result.

## Result

No configuration met the junk limit on no-match requests, so nothing is
adopted. The closest one missed it by one request in 64.

Primary agent `gpt-6.1-terra`, 178 matching and 64 no-match dev requests, 350
skills. Rates are of what the agent loads.

| Arm | Useful | Junk, matching | Junk, no-match | Shown on no-match | Characters shown |
|---|---|---|---|---|---|
| A0 shipped, no agent | 67.4% | 3.4% | 9.4% (6) | 32.8% | 80 |
| A1 shipped, agent may decline | 64.6% | 1.7% | 4.7% (3) | 32.8% | 80 |
| B lo 0.7, 1 shown, 120 chars | 73.0% | 2.2% | 10.9% (7) | 65.6% | 107 |
| B lo 0.7, 2 shown, 120 chars | 73.6% | 2.2% | 12.5% (8) | 65.6% | 114 |
| B lo 0.7, 1 shown, 300 chars | 74.2% | 2.2% | 15.6% (10) | 65.6% | 134 |
| B lo 0.7, 2 shown, 300 chars | 74.2% | 2.2% | 17.2% (11) | 65.6% | 147 |
| B lo 0.5, 1 shown, 120 chars | 74.2% | 2.2% | 12.5% (8) | 79.7% | 118 |
| B lo 0.5, 2 shown, 120 chars | 75.8% | 2.8% | 17.2% (11) | 79.7% | 137 |
| B lo 0.5, 1 shown, 300 chars | 75.3% | 3.4% | 18.8% (12) | 79.7% | 156 |
| B lo 0.5, 2 shown, 300 chars | 77.0% | 2.8% | 18.8% (12) | 79.7% | 192 |
| K no judge, top 2 | 61.2% | 2.2% | 14.1% (9) | 100% | 531 |
| K no judge, top 3 | 66.3% | 2.2% | 14.1% (9) | 100% | 792 |

Limits: junk at most 5% on matching and 10% on no-match requests (6 of 64);
adoption needs a useful rate of at least 72.4% (A0 plus five points). The
confirmation agent was not run because nothing was selected.

## What the numbers say

- Every band configuration clears the useful bar (+5.6 to +9.6 points) and
  lowers junk on matching requests. This is the first change that moves the
  useful rate by more than the bar. Korean gains less than English (+1.1 to
  +4.5 points against +10.3 to +14.8).
- The cost is on no-match requests. The agent loads one of the uncertain
  candidates there more often than the limit allows: 7 to 12 of 64 against 6
  for the shipped rule.
- Longer descriptions and more candidates make the agent load more, right and
  wrong alike. The 120-character cap is the more careful setting.
- The agent as a filter on confirmed hits (A1) halves junk on no-match
  requests (6 to 3) and costs 2.8 points of useful rate: it declines 5 right
  skills of 178.
- Without any judge (K, top 3), the agent reaches 66.3% useful with 14.1% junk
  on no-match requests. That is outside the limit, and it shows metadata on
  every request (about 790 characters). For comparison, on the fresh test set
  the local gate alone returned a wrong skill on 88.7% of no-match requests
  (`2026-11-24-precision-results.md`); the two numbers are from different
  request sets and count different things (returned against loaded).

## What this does not show

One model call stands in for an agent in the middle of a task, and the model
is not the one in the harnesses this project targets. The band holds 39
matching and 30 no-match requests, so the difference between 6 and 7 junk
loads is one request. The dev set has now been used six times. The result
says the idea is promising and unproven, not that it fails: a stricter
instruction to the agent, or a band starting at 0.8, could bring junk under
the limit, but choosing either now would be fitting to this dev set. A
follow-up needs new dev requests and its own protocol.
