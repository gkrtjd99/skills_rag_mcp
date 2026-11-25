# Agent in the loop, second attempt: results

Protocol: `2026-11-25-agent2-protocol.md` (committed as `a104f46` before the
dev set existed; addendum `09e85f1` before the no-match half of the test
existed). Script: `bench/scale/agent2.py`. Implementation committed as
`efe5cc7` before the test run.

## Outcome

- **Adopted, with a judge:** when no skill reaches 0.9, the single best skill
  at or above 0.7 is returned as an `uncertain` candidate and the calling
  agent decides. On the fresh test a simulated agent loaded a useful skill for
  67.0% of matching requests instead of 60.3%, and a wrong skill for 8.2% of
  no-match requests instead of 4.1%.
- **Not adopted, without a judge:** returning the top 3 of the local ranking
  as uncertain candidates. It halved wrong loads on no-match requests but the
  agent loaded a useful skill less often than with today's gate result, which
  fails the protocol. It remains available as
  `SKILL_RAG_LOCAL_CANDIDATES=3`, off by default.

All rates are of what the simulated agent loads, judged by the adjudicator.
A0 and G0 have no agent: the first returned skill counts as loaded.

## Selection on dev2

189 matching and 74 no-match requests (37 outside skills remained, not 50),
350 skills, primary agent `gpt-6.1-terra`.

| Arm | Useful | Junk, matching | Junk, no-match | Characters shown |
|---|---|---|---|---|
| A0 shipped, no agent | 69.3% | 0.5% | 6.8% (5) | 76 |
| A1 shipped, agent may decline | 65.1% | 0.5% | 6.8% (5) | 76 |
| B from 0.7, message M0 | 76.2% | 0.5% | 6.8% (5) | 103 |
| B from 0.7, message M1 (stricter) | 73.0% | 0.5% | 6.8% (5) | 103 |
| B from 0.8, message M0 | 74.1% | 0.5% | 6.8% (5) | 96 |
| B from 0.8, message M1 | 70.9% | 0.5% | 6.8% (5) | 96 |
| G0 gate, no agent | 53.4% | 41.8% | 86.5% (64) | 128 |
| G1 gate, agent decides (today without a key) | 73.0% | 3.7% | 13.5% (10) | 1,180 |
| K top 3, 300 characters, M0 | 73.0% | 1.6% | 6.8% (5) | 787 |
| K top 3, 120 characters, M1 | 54.0% | 1.1% | 0.0% (0) | 396 |

B from 0.7 with M0 was the only B configuration at or above the bar (A0 plus
five points, 74.3%). K with 300 characters and M0 was selected because G1
exceeds the junk limit on no-match requests. With the confirmation agent
`gpt-6-astra` both stayed inside the limits (B: 78.3% useful, 8.1% junk on
no-match; K: 73.5%, 5.4%).

In the band the primary agent loaded 29 skills on dev2 and the adjudicator
accepted all 29. The stricter message removed none of the wrong loads, which
all come from confirmed hits, and lost right ones.

## Fresh test

194 matching requests (`test3`) and 97 no-match requests (`test3neg`, see the
deviation below), run once.

| Arm | Useful | Junk, matching | Junk, no-match | Useful, English | Useful, Korean |
|---|---|---|---|---|---|
| A0 shipped, no agent | 60.3% | 3.1% | 4.1% (4) | 65.6% | 55.1% |
| A1 shipped, agent may decline | 58.2% | 2.1% | 3.1% (3) | 62.5% | 54.1% |
| **B from 0.7, M0 (adopted)** | 67.0% | 2.1% | 8.2% (8) | 70.8% | 63.3% |
| G0 gate, no agent | 56.7% | 39.2% | 78.4% (76) | 64.6% | 49.0% |
| G1 gate, agent decides | 69.6% | 4.1% | 14.4% (14) | 79.2% | 60.2% |
| K top 3, 300 characters, M0 | 62.9% | 4.6% | 7.2% (7) | 70.8% | 55.1% |

Confirmation agent: A1 58.8% / 2.1% / 3.1%; B 67.0% / 2.1% / 8.2%; G1 70.6% /
4.6% / 11.3%; K 63.4% / 2.6% / 5.2%.

- B passes: its useful rate is 6.7 points above A0's and both junk rates are
  inside the limits. It is not free: on no-match requests wrong loads go from
  4 to 8 of 97, and the share of no-match requests where anything is shown
  goes from 30% to 60%. Metadata shown per request rises from about 84 to 109
  characters on matching requests.
- K fails: its useful rate is below G1's (62.9% against 69.6%). It does cut
  wrong loads on no-match requests (14 to 7) and metadata shown (about 1,210
  to 800 characters), so it stays as an option for callers who prefer that
  trade.

## What else the numbers say

- An agent reading the gate's own result (G1) loads a useful skill about as
  often as the judged path does (69.6% against 67.0% on the test). What the
  judge buys is fewer wrong loads when nothing matches (8.2% against 14.4%)
  and far less metadata per search (about 110 characters against 1,210).
  Earlier documents compared the judge with G0, where every returned skill
  counts as loaded; that overstates what an agent without a judge does.
- The useful rate of the shipped rule differs by nine points between dev2
  (69.3%) and the test (60.3%). Differences between request sets are as large
  as the effects measured here; only comparisons within one set mean much.

## Deviations from the protocol

- `test3` came out with no no-match requests because no unused outside skill
  remained. Its no-match half was generated from the 50 `heldout` skills of
  the first scale test: never in a dev set, not in the corpus, new requests,
  but not unused. The rule for this and its decision bound were committed
  before those requests existed.
- dev2 has 74 no-match requests, not about 100, for the same reason.

## Limits

One model call with an empty context stands in for an agent in the middle of
a task, and neither agent model is the one in the harnesses this project
targets; a real agent may load uncertain candidates more or less readily. The
band was measured with `jev` only; `openai` probabilities sit closer to 0 and
1, so its band is likely small and is unmeasured. Requests are model-written,
and agents and adjudicator share a vendor. The first dev set gave 10.9% junk
on no-match requests for the adopted configuration (7 of 64), above the
limit; dev2 gave 6.8% and the test 8.2%.
