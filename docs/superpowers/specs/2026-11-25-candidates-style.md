# Candidates Style: Several Judged Skills for the Agent to Choose From

Date: 2026-11-25
Status: Implemented; measured with a simulated agent on a fresh test set

## Why

Putting every description in the agent's context loads a useful skill for 94
to 97% of matching requests; search that returned one sure skill did so for
67 to 77% (`docs/benchmarks/2026-11-25-native-baseline-results.md`). The gap
was the pipeline: the local shortlist missed the skill, and one judged skill
gave the agent nothing to choose from. The agent selects better than the
judge when it can see the candidates.

## Decision

1. `SKILL_RAG_RERANK_STYLE` selects the policy when a judge is configured:
   - `candidates` (default): every shortlisted skill with probability at or
     above `SKILL_RAG_RERANK_FLOOR` (0.5), ordered by probability, at most
     `SKILL_RAG_RERANK_SHOWN` (8), returned as
     `{status: "candidates", hits: [{name, description, score}], message}`.
     Descriptions are capped at 120 characters. `k` widens the shortlist but
     does not cap what is shown. Nothing at the floor is `no_match`.
   - `single`: the previous rule (0.9 and one skill, `uncertain` from 0.7).
2. `SKILL_RAG_RERANK_SCAN_MAX` defaults to 500 instead of 0: the judge scans
   the whole corpus to build the shortlist.
3. The bootstrap skill tells agents to load at most one candidate, only if it
   clearly fits, and not to search again with a reworded query.
4. Without a judge nothing changes.

## Evidence

`docs/benchmarks/2026-11-25-candidates-results.md`: on a fresh test set a
simulated agent loaded a useful skill for 91.1% of matching requests (74.9%
under `single`) and a wrong one for 9.4% of no-match requests (0.0% under
`single`; 54.2% with every description in context).

## Privacy

Changed. With a judge configured and the scan on (now the default), every
search sends every indexed skill's name and the first 120 characters of its
description to the provider, in addition to the query and the 16 shortlisted
descriptions. `SKILL_RAG_RERANK_SCAN_MAX=0` restores the earlier behaviour.
Bodies and paths are still never sent. `SECURITY.md` states this.

## Limits

The agent in the benchmark is one model call with an empty context. Only
`jev` was measured. Wrong loads on requests with no matching skill are higher
than under `single`. The usage log (`loaded after suggestion`) is the way to
see how a real agent treats candidates.
