# Baseline: every description in context, no search (fixed before it was run)

Written and committed on 2026-11-25 before the agent was shown the full skill
list for any request.

## Why

Every comparison so far has been between ways of searching. The alternative
this project replaces has not been measured: the harness puts every skill's
name and description in the agent's context and the agent picks. If that
loads the right skill much more often, the project trades accuracy for
context and must say so. If it does not, the remaining misses are a property
of the descriptions and not of the search.

## What is run

No configuration is selected, so no new requests are needed. The requests of
two sets already measured are reused, with the same 350 skills and the same
adjudicator:

- the fresh test of the uncertain-band work: `test3` (194 matching) and
  `test3neg` (97 no-match), where the shipped default and the no-judge path
  have recorded results;
- `dev3` (184 matching, 96 no-match), where the shipped default and the
  judge's whole-corpus scan have recorded results.

Arms, each one model call per request:

- **ALL**: all 350 skills as `- name: description`, full descriptions as
  published, in alphabetical order of name.
- **ALL120**: the same list with descriptions cut to 120 characters. Test set
  only.

Developer message, verbatim, followed by the list:

> You are an AI coding agent working on a user's request. The skills available
> to you are listed below, one per line as name: description. A skill is a set
> of instructions you can load in full with get_skill(name). Loading costs
> context, so load a skill only if its name and description show that it
> covers this specific task on the same product, platform, or technology.
> Decide which single skill to load, or none. Answer as JSON.

User message: `User request: <request>`. The answer is `{"load": <name or
null>}`; a name not in the list counts as loading nothing and is reported.
The sentence about when to load is the one the search arms used.

Primary agent `gpt-6.1-terra` on everything; confirmation agent `gpt-6-astra`
on ALL for the test set.

## What is reported

Useful rate, junk on matching requests, junk on no-match requests, by
language, and the input tokens per request (total and cached), next to the
recorded results of the search arms on the same requests.

## How the result will be read

Stated now so it cannot be bent later. On the test set, primary agent,
against the shipped default (67.0% useful, 8.2% junk on no-match):

- ALL at least five points higher in useful rate with junk on no-match no
  higher than the shipped default's plus three points: the READMEs must say
  that search gives up accuracy to save context, with both numbers.
- ALL within five points either way: the READMEs may say search is comparable
  at a fraction of the context, with both numbers.
- ALL at least five points lower, or its junk on no-match more than three
  points higher at a comparable useful rate: the READMEs may say search is
  better at this corpus size, with both numbers.

## Limits known in advance

One corpus size (350). A harness may order, truncate, or budget its skill
list differently, and its agent sees the list inside a long system prompt
with a task in progress, not alone. The agent may load one skill here; a real
agent may load several. Both request sets were built for search experiments
(requests never name a skill). The agent models are not the ones in the
targeted harnesses.
