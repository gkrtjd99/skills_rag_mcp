# Whole-corpus scan with the agent in the loop: selection protocol (fixed before its data existed)

Written and committed on 2026-11-25 before a `dev3` request was generated and
before any scan, judgment, or agent decision was made on one. `jev` only.

## Why

For about 16% of matching requests the right skill is not among the 16
candidates the judge sees, and nothing downstream can recover it. Letting the
judge scan every skill put the right skill in the top 16 for 97% of dev
requests against 74% for the local ranking
(`2026-11-24-precision-results.md`), but the scan was left off because it also
returned more skills that did not fit. That was counted as "returned means
loaded". Since then a simulated agent has been shown to decline most wrong
candidates (`2026-11-25-agent2-results.md`). The question is whether the scan
pays once the agent decides what to load.

## Data

- `dev3` (`prepare.py dev3`, seed 20261129): 50 targets from the 100 corpus
  skills no earlier set used as targets, two requests per language; no-match
  requests, one per language, from 50 skills of
  `candidates-2026-11-25.json`. That file lists the skills on
  `https://skills.sh/hot` and `https://skills.sh/trending` on 2026-11-25 that
  are not in the first snapshot (508 entries, 62 sources), in page order; the
  acceptance rules for a no-match source are those of `dev2`.
- `test4` (`prepare.py test4`, seed 20261130): the remaining 50 targets and 50
  further skills of that file. Built only if something is adopted.
- Corpus, generator, name rule, and adjudicator as before.

`bench/scale/scan_agent.py record <set>` stores per request: the local
shortlist of 16; the top 16 of the judge's scan over all 350 skills (shipped
scan wording, 120 characters of description); the yes/no probability of every
skill in either list; scan tokens and latency.

## Arms

The decision rule is the shipped one in every arm: the top candidate at or
above 0.9 is returned as confirmed; otherwise the best in [0.7, 0.9) is
returned as uncertain (shipped message); otherwise nothing. The simulated
agent and its developer message are those of `2026-11-25-agent-protocol.md`.
Only the shortlist differs:

- **L**: local shortlist (shipped).
- **S**: scan shortlist, as `SKILL_RAG_RERANK_SCAN_MAX` builds it.
- **S9**: scan shortlist with the uncertain band off (0.9 and above only).

Also reported, without an agent (first returned skill counted as loaded): L0
and S0; and for each shortlist the share of matching requests whose expected
skill is in it.

## Selection, adoption, confirmation

Primary agent `gpt-6.1-terra`. S or S9 qualifies if junk is at most 10% on
no-match and 5% on matching requests. A qualifying arm is a candidate if its
useful rate exceeds L's by at least five points. If both are candidates, the
one with the higher useful rate is taken; within one point, the one with the
lower junk rate on no-match requests.

The selected arm is run with the confirmation agent `gpt-6-astra`; if it
exceeds a junk limit there it is not adopted.

If adopted, the default of `SKILL_RAG_RERANK_SCAN_MAX` is raised (and the band
default changed if S9 won), committed, and the arm is run once on `test4`
against L with both agents. It stays only if, with the primary agent, its
useful rate is higher than L's and neither junk rate is above its limit by
more than three points.

If nothing is adopted the result is reported as negative and `test4` is not
built.

## Costs to report

Scan input tokens and added latency per search at 350 skills, and what is
sent: with the scan every skill's name and first 120 characters of description
go to the provider on every search, instead of 16 names and descriptions.

## Limits known in advance

The simulated agent is one model call with an empty context and is not the
model of a targeted harness. Requests are model-written. The no-match sources
come from a second snapshot of the same site and may be closer to or further
from the corpus than the first snapshot's. The corpus has 350 skills; the
scan's cost grows with the corpus and its benefit may too.
