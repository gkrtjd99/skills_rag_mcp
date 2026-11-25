# Several candidates for the agent: selection protocol (fixed before any such result was shown to an agent)

Written and committed on 2026-11-25 before an agent was shown a list of
several candidates for any request. `jev` only.

## Why

Two extremes have been measured (`2026-11-25-native-baseline-results.md`).
Search shows the agent at most one skill: few wrong loads, and a useful skill
for 67 to 82% of matching requests. Putting all 350 descriptions in context
gets 94 to 97%, with a wrong load for a third of no-match requests and about
34,000 tokens of standing context. The agent is the better selector when it
can see the candidates; the question is how few candidates are enough, and
whether a floor on the judge's probability keeps wrong loads down.

## Data

- Selection: `dev3` (184 matching, 96 no-match), already recorded by
  `scan_agent.py record`: local shortlist of 16, the judge's scan shortlist of
  16, the yes/no probability of each. This is its second use; its first
  compared two shortlists under the shipped rule.
- Confirmation: `test4` (`prepare.py test4`, seed 20261130), never built so
  far: the last 50 unused corpus targets and 50 further outside skills.

## Arms

The agent and its developer message are those of
`2026-11-25-agent-protocol.md`. A result with several candidates is

```json
{"status": "candidates",
 "hits": [{"name": "...", "description": "... (120 characters)", "score": 0.83}],
 "message": "These are the closest skills, best first. Often none of them fits: load one only if its name and description clearly cover this task; otherwise proceed without a skill."}
```

- **C:source:n:floor**: the skills of the shortlist (`scan` or `local`) whose
  yes/no probability is at least `floor`, ordered by that probability, at most
  `n` of them; nothing is shown if none reaches the floor. `n` in 3, 8;
  `floor` in 0.1, 0.5. Eight configurations.
- **N:n**: no judge at all. The top `n` of the local hybrid ranking, without
  scores. `n` in 8, 16. Two configurations.

Reported next to them on the same requests: L (shipped), S (scan shortlist
under the shipped rule), ALL (every description in context).

## Selection

Primary agent `gpt-6.1-terra`. A configuration qualifies if junk is at most
10% on no-match and 5% on matching requests. It is a candidate if its useful
rate exceeds L's by at least five points. The candidate with the highest
useful rate is selected; among those within one point of it, the one that
needs no scan, then the smaller `n`, then the higher floor. N arms are
selected the same way and compete with C arms; a selected N arm changes the
behaviour without a judge only.

The selected configuration is run with the confirmation agent `gpt-6-astra`;
if it exceeds a junk limit there it is not adopted.

## Confirmation

An adopted configuration is implemented and committed, then run once on
`test4` against L, with both agents, and ALL is run on `test4` with the
primary agent for reference. The configuration stays the default only if,
with the primary agent, its useful rate is higher than L's and neither junk
rate is above its limit by more than three points.

If nothing is adopted the result is reported as negative and `test4` is not
built.

## Costs to report

Characters of metadata shown per request, judge tokens (scan and fit), and
latency, for the selected configuration and for L.

## Limits known in advance

As before: one model call with an empty context stands in for an agent;
requests are model-written; the agent models are not those of the targeted
harnesses; one corpus size. Ten configurations on 280 requests invite a lucky
winner, which is what the fresh test is for.
