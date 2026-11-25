# Letting the agent decide the uncertain band: selection protocol (fixed before any agent decision was collected)

Written and committed on 2026-11-25 before a model was asked to act as the
agent on any request. It extends `2026-11-24-precision-protocol.md`.

## Why

Of matching dev requests, 13% lose the right skill because the judge scores it
below 0.9 although it is among the 16 candidates. Four changes to the judge's
evidence or question did not recover them (`2026-11-24-cards-results.md`,
`2026-11-24-structure-results.md`). The caller of `search_skills` is itself a
much stronger model than the judge and reads the result anyway. The question
is whether showing it a few unconfirmed candidates, clearly marked, recovers
right skills without making it load wrong ones. Showing a candidate costs a
line of metadata; loading a wrong skill costs its whole body, so the outcome
that is counted is what the agent loads.

A second question rides along: whether the agent can decide without any judge,
which would matter for installs that have no provider key.

## Data

The dev set of the precision protocol: 178 matching and 64 no-match requests,
350 skills, the recorded local shortlist of 16 and the recorded `jev` yes/no
probability of each candidate, the same adjudicator (`gpt-6.2-sol`, which sees
the opening of the skill body). This is the sixth use of the dev set.

## The simulated agent

One request to a model per (request, search result). Primary agent
`gpt-6.1-terra`; confirmation agent `gpt-6-astra`. Neither is the adjudicator.
The agent sees the request and the search result only (names and capped
descriptions, never a body), as a real caller does before `get_skill`.
Developer message, verbatim:

> You are an AI coding agent working on a user's request. Before starting you
> searched a skill library; the search result is below. A skill is a set of
> instructions you can load in full with get_skill(name). Loading costs
> context, so load a skill only if its name and description show that it
> covers this specific task on the same product, platform, or technology.
> Hits marked "confidence": "low" are uncertain candidates that the search
> could not confirm. Decide which single skill to load, or none. Answer as
> JSON.

User message: `User request: <request>` then `search_skills result:` and the
result as JSON. The answer is `{"load": <name or null>}`; a name that was not
shown counts as loading nothing and is reported.

Result shapes:

- confirmed: `{"status": "ok", "hits": [{"name", "description", "score"}]}`,
  description capped at 120 characters, as shipped;
- uncertain: `{"status": "uncertain", "hits": [{"name", "description",
  "confidence": "low"}], "message": "No skill was confirmed for this request.
  These are uncertain candidates: load one only if its description clearly
  covers the task; otherwise proceed without a skill."}`;
- nothing shown: the agent is not asked and loads nothing.

## Arms

- **A0, shipped as measured so far.** The top candidate at or above 0.9 is
  returned and counted as loaded. No agent.
- **A1, shipped with the agent.** The same result; the agent may decline it.
- **B, uncertain band.** As A1 when a candidate reaches 0.9. Otherwise the top
  `m` candidates with probability in [`lo`, 0.9) are shown as uncertain, with
  descriptions capped at `d` characters. `lo` in 0.5, 0.7; `m` in 1, 2; `d` in
  120, 300. Eight configurations.
- **K, no judge.** The top `n` candidates of the local hybrid ranking are
  shown as uncertain, `d` = 300, no probabilities used. `n` in 2, 3.

## What is counted

Per arm, from what the agent loads: the share of matching requests where it
loads a skill that is the expected one or that the adjudicator accepts
(useful); the share of matching requests and of no-match requests where it
loads a skill that is neither (junk). Also reported: the share of requests
where anything is shown, the mean characters of metadata shown per request,
how often the agent declines a confirmed hit that was right, and results by
language. Agent answers are cached by model, messages, and result.

## Selection, adoption, confirmation

A configuration qualifies if, with the primary agent, junk is at most 10% on
no-match and 5% on matching requests. It is a candidate for adoption only if
its useful rate exceeds A0's by at least five points. Among candidates within
one point of the best, the one showing the fewest characters wins. B and K are
selected separately; K is adopted only as the behaviour without a provider
key and is compared with the local gate as well as with A0.

The selected configuration is then run with the confirmation agent. If its
junk rates exceed the limits there, the result is reported as dependent on the
agent and nothing is adopted.

An adopted configuration is implemented and committed, and then run once on a
fresh test set built as `test2` was (new seed 20261127, 50 targets among
corpus skills never used as targets, no-match requests from candidates that
never entered the pool and were not used by `test2`; fewer if fewer remain),
against A0 on the same requests, with both agents. It stays only if its useful
rate is higher than A0's there and neither junk rate is more than three points
higher, with the primary agent.

If nothing is adopted the result is reported as negative and no test set is
used.

## Limits known in advance

The agent is one model call with nothing else in its context; a real agent
decides in the middle of a task and may behave differently. Neither agent
model is the one in the harnesses this project targets. Requests are
model-written, and the agents and the adjudicator come from one vendor. The
agent decides from descriptions as published; a description that oversells
its skill would be loaded. 242 requests cannot resolve differences of two or
three points. The uncertain band holds 39 matching and 30 no-match dev
requests, so its own rates rest on small counts.
