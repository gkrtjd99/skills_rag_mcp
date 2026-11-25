# Agent in the loop, second attempt: selection protocol (fixed before the new dev set existed)

Written and committed on 2026-11-25 before a `dev2` request was generated and
before any judge or agent saw one. It follows
`2026-11-25-agent-results.md`.

## Why

Showing the agent one unconfirmed candidate raised the useful rate by 5.6
points on the first dev set but exceeded the junk limit on no-match requests
by one request in 64. That set has been used six times and the uncertain band
on it holds 69 requests, so the miss cannot be told from noise and nothing may
be tuned on it. This protocol tests a small number of more careful
configurations on new requests, with more no-match requests.

## Data

`dev2`, built by `bench/scale/prepare.py dev2` (seed 20261128): 50 targets
drawn from the corpus skills that no earlier set used as targets, two requests
per language each; no-match requests, one per language, from 50 skills that
never entered the pool and were not used by `test2`. Same generator, same
rule for dropping requests that name their skill, same 350-skill corpus, same
adjudicator. `bench/scale/agent2.py record dev2` stores, per request, the
local shortlist of 16, the `jev` yes/no probability of each, and the result
the local gate returns for `k` = 5.

## Arms

The simulated agent, its developer message, and the result shapes are those of
`2026-11-25-agent-protocol.md`. Two texts for the message of an uncertain
result:

- **M0**, as before: "No skill was confirmed for this request. These are
  uncertain candidates: load one only if its description clearly covers the
  task; otherwise proceed without a skill."
- **M1**, stricter: "No skill was confirmed for this request. Listed below:
  unconfirmed candidates only. Most unconfirmed candidates are wrong. Load one
  only if its name and description state this exact task on the same product
  or tool; if the match depends on reading the description generously,
  proceed without a skill."

Arms:

- **A0**: shipped rule (top candidate at or above 0.9), counted as loaded.
- **A1**: the same result, the agent may decline.
- **B**: as A1, and when nothing reaches 0.9 the single best candidate with
  probability in [`lo`, 0.9) is shown as uncertain with a 120-character
  description. `lo` in 0.7, 0.8; message M0 or M1. Four configurations.
- **G0**: no judge; the first hit of the local gate, counted as loaded.
- **G1**: no judge; the gate's result as returned today, the agent decides.
  This is what an install without a provider key does now.
- **K**: no judge; the top 3 of the local ranking shown as uncertain: 300
  characters with M0, or 120 characters with M1. Two configurations.

## Selection

Primary agent `gpt-6.1-terra`. A configuration qualifies if junk is at most
10% on no-match and 5% on matching requests.

- **B** is a candidate if it qualifies and its useful rate exceeds A0's by at
  least five points. Among candidates within one point of the best, fewest
  characters shown wins, then the higher `lo`, then M1.
- **K** is a candidate for installs without a key if it qualifies and either
  G1 does not qualify or K's useful rate exceeds G1's by at least five points.
  Between two K candidates, the higher useful rate wins.

A selected configuration is run with the confirmation agent `gpt-6-astra`; if
it exceeds a junk limit there, the result is reported as dependent on the
agent and it is not adopted.

## Confirmation on a fresh test

An adopted configuration is implemented and committed, then run once on
`test3` (`prepare.py test3`, seed 20261127, built like `dev2` from skills that
neither `dev2` nor any earlier set used), with both agents, against its
baseline on the same requests (A0 for B, G1 for K). It stays only if, with the
primary agent, its useful rate is higher than the baseline's and neither junk
rate is above the limits by more than three points.

If nothing is adopted, the result is reported as negative and `test3` is not
built.

## Limits known in advance

As in the first protocol: one model call stands in for an agent that would be
in the middle of a task; the agent models are not the ones in the targeted
harnesses; requests are model-written; agents and adjudicator share a vendor.
The wording M1 was written after seeing the first dev result, so it is tested
only on requests that did not exist then.

## Addendum: no-match requests for the fresh test (written before any existed)

Added on 2026-11-25 after `prepare.py test3` produced 194 matching requests
and no no-match request: every candidate skill outside the pool had been used
by `test2` or `dev2`. The matching half of `test3` has been scored; no
no-match request for the test has been generated or scored at the time of
this commit.

Deviation: the no-match half is generated from the 50 `heldout` skills of
`split.json` (`prepare.py test3neg`, one request per language). These skills
are not in the 350-skill corpus. They were the no-match sources of the first
scale test set, which is retired; they were never part of a dev set, so no
threshold, wording, or configuration was chosen on them. The requests are
newly generated. This is weaker than the protocol's "skills no earlier set
used" and is reported as such.

Decision on these requests, primary agent: B stays if its junk rate on them is
at most 13% (the limit plus three points). K is already rejected by the
matching half (its useful rate is below G1's) and is reported only.
